import logging
import os
import tarfile
import tempfile
import uuid
from typing import Optional

try:
    import docker
    from docker.errors import DockerException, ImageNotFound
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

logger = logging.getLogger(__name__)

class SecureExecutionSandbox:
    """Executes commands inside an isolated Docker container.
    
    Mounts a specific workspace directory into the container to allow agents
    to run scripts, install dependencies, or execute test suites securely.
    """

    def __init__(self, default_image: str = "python:3.12-slim"):
        self.default_image = default_image
        self.client = None
        if DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
                # Test connection
                self.client.ping()
            except DockerException as e:
                logger.warning("Docker daemon is not available: %s", e)
                self.client = None

    def is_available(self) -> bool:
        """Return True if Docker is installed and the daemon is running."""
        return self.client is not None

    def execute_command(
        self,
        command: str,
        workspace_dir: str,
        image: Optional[str] = None,
        timeout: int = 120,
    ) -> dict:
        """Run a command inside a Docker container mounted to the workspace.

        Parameters
        ----------
        command:
            The shell command to run (e.g. "pytest tests/").
        workspace_dir:
            The absolute path on the host to mount into the container at /workspace.
        image:
            Docker image to use. Defaults to `python:3.12-slim` if None.
        timeout:
            Maximum execution time in seconds.

        Returns
        -------
        dict
            {"exit_code": int, "output": str, "error": str}
        """
        if not self.is_available():
            return {
                "exit_code": 1,
                "output": "",
                "error": "Docker is not available on this host. Cannot execute in sandbox.",
            }

        image = image or self.default_image
        container_name = f"aidevos_sandbox_{uuid.uuid4().hex[:8]}"
        
        try:
            # Ensure the image exists
            try:
                self.client.images.get(image)
            except ImageNotFound:
                logger.info("Pulling image %s...", image)
                self.client.images.pull(image)

            # We use bind mounts to mount the workspace dir.
            # Convert Windows path to Docker compatible path if necessary,
            # but Docker for Windows usually handles absolute paths fine in bind mounts.
            volumes = {
                os.path.abspath(workspace_dir): {
                    "bind": "/workspace",
                    "mode": "rw"
                }
            }

            logger.info("Starting sandbox container %s in %s", container_name, workspace_dir)
            container = self.client.containers.run(
                image,
                command=["sh", "-c", command],
                name=container_name,
                volumes=volumes,
                working_dir="/workspace",
                detach=True,
                network_disabled=False,  # Allows npm install etc.
                mem_limit="1g",
            )

            # Wait for the container to finish or timeout
            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", 1)
            except Exception as e:
                # Timeout or other error waiting
                container.kill()
                exit_code = 124  # timeout exit code
            
            logs = container.logs().decode("utf-8", errors="replace")
            
            return {
                "exit_code": exit_code,
                "output": logs if exit_code == 0 else "",
                "error": logs if exit_code != 0 else "",
            }
            
        except Exception as e:
            logger.error("Sandbox execution failed: %s", e)
            return {
                "exit_code": 1,
                "output": "",
                "error": f"Sandbox error: {str(e)}",
            }
        finally:
            # Cleanup
            if self.client:
                try:
                    c = self.client.containers.get(container_name)
                    c.remove(force=True)
                except docker.errors.NotFound:
                    pass
                except Exception as e:
                    logger.warning("Failed to remove container %s: %s", container_name, e)
