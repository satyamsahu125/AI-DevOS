import type { Data } from "@measured/puck"
import type { ComponentSpec, DesignArtifact } from "@/types/design"

export function designArtifactToPuck(design: DesignArtifact): Data {
  const content: Data["content"] = []

  if (design && design.pages) {
    for (const page of design.pages) {
      if (page.components) {
        for (const componentId of page.components) {
          const spec = (design.components || []).find((c) => c.component_id === componentId)
          if (!spec) continue

          const puckComponent = mapComponentToPuck(spec)
          if (puckComponent) content.push(puckComponent)
        }
      }
    }
  }

  if (content.length === 0 && design && design.components && design.components.length > 0) {
    for (const spec of design.components) {
      const puckComponent = mapComponentToPuck(spec)
      if (puckComponent) content.push(puckComponent)
    }
  }

  return {
    content,
    root: {
      // Puck accepts custom root props at runtime, but its Data type only
      // models `title`, so widen just this object rather than the whole Data.
      props: {
        title: design?.project_name || "Design Review",
        background: design?.color_palette?.background || "#FFFFFF",
        fontFamily: design?.typography?.heading_font || "Inter",
      } as Data["root"]["props"],
    },
  }
}

function mapComponentToPuck(spec: ComponentSpec) {
  const mapping: Record<string, string> = {
    Hero: "HeroSection",
    HeroSection: "HeroSection",
    Card: "CardGrid",
    CardGrid: "CardGrid",
    NavigationMenu: "NavigationBar",
    NavigationBar: "NavigationBar",
    Navbar: "NavigationBar",
    Form: "FormSection",
    FormSection: "FormSection",
    Table: "DataTable",
    DataTable: "DataTable",
    Sheet: "Sidebar",
    Sidebar: "Sidebar",
  }

  const puckType = mapping[spec.shadcn_component] || mapping[spec.name] || mapping[spec.type || ""]
  if (!puckType) return null

  return {
    type: puckType,
    props: {
      ...spec.props,
    },
  }
}

function buildTailwindFromProps(props: Record<string, any>): string {
  const classes: string[] = []
  if (props?.layout) classes.push(`text-${props.layout}`)
  if (props?.columns) classes.push(`grid-cols-${props.columns}`)
  return classes.join(" ")
}

export function puckToDesignArtifact(puckData: Data, originalDesign: DesignArtifact): DesignArtifact {
  return {
    ...originalDesign,
    components: puckData.content.map((item, i) => ({
      component_id: `component_${i}`,
      name: item.type as string,
      shadcn_component: (item.type as string).replace("Section", "").replace("Bar", "Menu"),
      tailwind_classes: buildTailwindFromProps(item.props || {}),
      props: item.props || {},
      states: { default: "", loading: "opacity-75" },
    })),
    review_iteration: (originalDesign?.review_iteration || 1) + 1,
    user_modified: true,
  }
}
