import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Sign In - AI TaskManagement OS",
    description: "Sign in to AI TaskManagement OS",
};

export default function AuthLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    // Auth pages don't need the main sidebar layout
    return <>{children}</>;
}
