export interface ComponentSpec {
  component_id: string
  name: string
  type?: string
  shadcn_component: string
  tailwind_classes?: string
  animation_component?: string | null
  animation_trigger?: string | null
  cult_ui_pattern?: string | null
  dark_mode_classes?: string
  children?: string[]
  props?: Record<string, any>
  states?: Record<string, any> | string[]
  description?: string
  purpose?: string
  inputs?: string[]
  outputs?: string[]
}

export interface PageSpec {
  page_id: string
  name: string
  route?: string
  layout?: string
  components: string[]
  description?: string
}

export interface DesignArtifact {
  project_id: string
  project_name: string
  animation_library?: string
  ui_pattern?: string
  design_system?: Record<string, any>
  color_palette: {
    primary?: string
    secondary?: string
    background?: string
    surface?: string
    text_primary?: string
    text_secondary?: string
    error?: string
    warning?: string
    success?: string
  }
  typography: {
    heading_font?: string
    body_font?: string
    heading_sizes?: Record<string, string>
    body_size?: string
    line_height?: string
  }
  pages: PageSpec[]
  components: ComponentSpec[]
  user_flows?: any[]
  navigation?: Record<string, any>
  review_iteration: number
  previous_feedback?: string | null
  user_modified?: boolean
}
