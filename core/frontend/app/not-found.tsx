import Link from "next/link";

export default function NotFound() {
    return (
        <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-950 text-gray-100">
            <div className="w-full max-w-md px-8 text-center">
                <div className="mb-6 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-gray-900 shadow-xl shadow-blue-900/10">
                    <span className="text-4xl">🔍</span>
                </div>
                <h2 className="mb-3 text-2xl font-bold">Page Not Found</h2>
                <p className="mb-8 text-gray-400">
                    We couldn't find the page you were looking for. It might have been
                    removed, renamed, or doesn't exist.
                </p>
                <Link
                    href="/"
                    className="inline-flex w-full items-center justify-center rounded-xl bg-blue-600 px-6 py-3 font-semibold text-white transition-all hover:bg-blue-500 hover:shadow-lg hover:shadow-blue-600/20 active:scale-95"
                >
                    Return Home
                </Link>
            </div>
        </div>
    );
}
