import { Nav } from "@/components/nav"
import { Footer } from "@/components/footer"

export default function MainLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-navy-light focus:px-4 focus:py-2 focus:text-gold"
      >
        Skip to content
      </a>
      <Nav />
      <main id="main-content" className="min-h-screen pt-16">{children}</main>
      <Footer />
    </>
  )
}
