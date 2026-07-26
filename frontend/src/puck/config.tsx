import type { Config } from "@measured/puck"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"

// Puck's array fields are untyped at the Config level, so the render callbacks
// below receive implicitly-any items. These describe the shapes declared in each
// component's arrayFields/defaultProps so the renders stay type-checked.
interface CardItem { title?: string; description?: string; badge?: string }
interface LinkItem { label?: string; href?: string }
interface FormFieldItem { label?: string; type?: string; placeholder?: string }
interface ColumnItem { header?: string }
interface NavItem { icon?: string; label?: string; active?: boolean }

export const puckConfig: Config<Record<string, any>> = {
  components: {
    HeroSection: {
      label: "Hero Section",
      fields: {
        title: { type: "text" },
        subtitle: { type: "textarea" },
        ctaText: { type: "text" },
        ctaVariant: {
          type: "select",
          options: [
            { label: "Primary", value: "default" },
            { label: "Secondary", value: "secondary" },
            { label: "Outline", value: "outline" },
          ],
        },
        layout: {
          type: "select",
          options: [
            { label: "Centered", value: "center" },
            { label: "Left", value: "left" },
          ],
        },
      },
      defaultProps: {
        title: "Welcome",
        subtitle: "Your subtitle here",
        ctaText: "Get Started",
        ctaVariant: "default",
        layout: "center",
      },
      render: ({ title, subtitle, ctaText, ctaVariant, layout }: any) => (
        <section className={`py-20 px-6 text-${layout}`}>
          <h1 className="text-4xl font-bold tracking-tight">{title}</h1>
          <p className="mt-4 text-xl text-muted-foreground">{subtitle}</p>
          <Button variant={ctaVariant} className="mt-8">
            {ctaText}
          </Button>
        </section>
      ),
    },

    CardGrid: {
      label: "Card Grid",
      fields: {
        columns: {
          type: "select",
          options: [
            { label: "2 columns", value: "2" },
            { label: "3 columns", value: "3" },
            { label: "4 columns", value: "4" },
          ],
        },
        cards: {
          type: "array",
          arrayFields: {
            title: { type: "text" },
            description: { type: "textarea" },
            badge: { type: "text" },
          },
        },
      },
      defaultProps: {
        columns: "3",
        cards: [{ title: "Feature 1", description: "Description", badge: "New" }],
      },
      render: ({ columns, cards }: any) => (
        <div className={`grid grid-cols-${columns} gap-6 p-6`}>
          {(cards || []).map((card: CardItem, i: number) => (
            <Card key={i} className="p-6">
              <Badge>{card.badge}</Badge>
              <h3 className="mt-2 font-semibold">{card.title}</h3>
              <p className="text-muted-foreground">{card.description}</p>
            </Card>
          ))}
        </div>
      ),
    },

    NavigationBar: {
      label: "Navigation Bar",
      fields: {
        logo: { type: "text" },
        links: {
          type: "array",
          arrayFields: {
            label: { type: "text" },
            href: { type: "text" },
          },
        },
        showAuthButtons: {
          type: "radio",
          options: [
            { label: "Yes", value: true },
            { label: "No", value: false },
          ],
        },
      },
      defaultProps: {
        logo: "MyApp",
        links: [
          { label: "Home", href: "/" },
          { label: "About", href: "/about" },
        ],
        showAuthButtons: true,
      },
      render: ({ logo, links, showAuthButtons }: any) => (
        <nav className="flex items-center justify-between px-6 py-4 border-b">
          <span className="font-bold text-xl">{logo}</span>
          <div className="flex gap-6">
            {(links || []).map((link: LinkItem, i: number) => (
              <a key={i} href={link.href} className="text-muted-foreground hover:text-foreground">
                {link.label}
              </a>
            ))}
          </div>
          {showAuthButtons && (
            <div className="flex gap-2">
              <Button variant="outline">Login</Button>
              <Button>Sign Up</Button>
            </div>
          )}
        </nav>
      ),
    },

    FormSection: {
      label: "Form Section",
      fields: {
        title: { type: "text" },
        fields: {
          type: "array",
          arrayFields: {
            label: { type: "text" },
            type: {
              type: "select",
              options: [
                { label: "Text", value: "text" },
                { label: "Email", value: "email" },
                { label: "Password", value: "password" },
                { label: "Textarea", value: "textarea" },
              ],
            },
            placeholder: { type: "text" },
          },
        },
        submitText: { type: "text" },
      },
      defaultProps: {
        title: "Contact Us",
        fields: [
          { label: "Name", type: "text", placeholder: "Your name" },
          { label: "Email", type: "email", placeholder: "your@email.com" },
        ],
        submitText: "Submit",
      },
      render: ({ title, fields, submitText }: any) => (
        <Card className="max-w-md mx-auto p-6">
          <h2 className="text-2xl font-bold mb-4">{title}</h2>
          <div className="space-y-4">
            {(fields || []).map((field: FormFieldItem, i: number) => (
              <div key={i}>
                <label className="text-sm font-medium">{field.label}</label>
                <Input type={field.type} placeholder={field.placeholder} className="mt-1" />
              </div>
            ))}
            <Button className="w-full">{submitText}</Button>
          </div>
        </Card>
      ),
    },

    DataTable: {
      label: "Data Table",
      fields: {
        title: { type: "text" },
        columns: {
          type: "array",
          arrayFields: { header: { type: "text" } },
        },
      },
      defaultProps: {
        title: "Data Table",
        columns: [{ header: "Name" }, { header: "Status" }, { header: "Date" }],
      },
      render: ({ title, columns }: any) => (
        <div className="p-6">
          <h3 className="font-semibold mb-4">{title}</h3>
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-muted">
                <tr>
                  {(columns || []).map((col: ColumnItem, i: number) => (
                    <th key={i} className="px-4 py-3 text-left text-sm font-medium">
                      {col.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-t">
                  {(columns || []).map((_: ColumnItem, i: number) => (
                    <td key={i} className="px-4 py-3 text-sm text-muted-foreground">
                      Sample data
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ),
    },

    Sidebar: {
      label: "Sidebar Layout",
      fields: {
        items: {
          type: "array",
          arrayFields: {
            icon: { type: "text" },
            label: { type: "text" },
            active: {
              type: "radio",
              options: [
                { label: "Yes", value: true },
                { label: "No", value: false },
              ],
            },
          },
        },
      },
      defaultProps: {
        items: [
          { icon: "🏠", label: "Dashboard", active: true },
          { icon: "👤", label: "Profile", active: false },
          { icon: "⚙️", label: "Settings", active: false },
        ],
      },
      render: ({ items }: any) => (
        <aside className="w-64 min-h-screen border-r p-4">
          <nav className="space-y-1">
            {(items || []).map((item: NavItem, i: number) => (
              <div
                key={i}
                className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer ${
                  item.active ? "bg-accent font-medium" : "hover:bg-muted"
                }`}
              >
                <span>{item.icon}</span>
                <span className="text-sm">{item.label}</span>
              </div>
            ))}
          </nav>
        </aside>
      ),
    },
  },
} as any
