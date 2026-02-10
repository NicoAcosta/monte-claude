import { Nav } from "@/components/nav"
import { Footer } from "@/components/footer"

export default function MainLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      <Nav />
      <main className="min-h-screen pt-16">{children}</main>
      <Footer />
    </>
  )
}
