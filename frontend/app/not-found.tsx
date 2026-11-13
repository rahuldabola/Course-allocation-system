import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <p className="text-sm font-semibold text-brand-600 dark:text-brand-400">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
        The page you&apos;re looking for doesn&apos;t exist.
      </p>
      <Link href="/" className="btn-primary mt-6">
        Back to dashboard
      </Link>
    </div>
  );
}
