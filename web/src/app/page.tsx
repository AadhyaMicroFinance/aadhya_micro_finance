"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Route users to their workspace when already signed in. */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const signedIn = Boolean(localStorage.getItem("access_token"));
    router.replace(signedIn ? "/dashboard" : "/login");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center text-sm text-surface-500">
      Loading…
    </main>
  );
}
