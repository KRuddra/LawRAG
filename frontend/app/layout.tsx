import './globals.css'

export const metadata = {
  title: 'Legal Chat — US & Canada',
  description: 'Ask questions about statutes and regulations across US and Canadian jurisdictions',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-dark-bgPrimary text-dark-textPrimary">
        {children}
      </body>
    </html>
  )
}

