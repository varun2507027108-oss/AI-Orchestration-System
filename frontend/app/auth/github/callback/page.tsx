'use client';

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BACKEND_URL } from "@/lib/config";

function GitHubCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get("code");
  const [error, setError] = useState(false);

  useEffect(() => {
    if (code) {
      fetch(`${BACKEND_URL}/auth/github?code=${code}`)
        .then(res => res.json())
        .then(data => {
          if (data.access_token) {
            localStorage.setItem("github_token", data.access_token);
            router.push("/start");
          } else {
            setError(true);
          }
        })
        .catch(() => setError(true));
    }
  }, [code, router]);

  if (error) {
    return (
      <div className="p-10 text-center text-red-500">
        Authentication failed.{" "}
        <button onClick={() => router.push("/start")} className="underline hover:text-red-400">
          Go back
        </button>
      </div>
    );
  }
  return <div className="p-10 text-center animate-pulse text-text-muted">Connecting to GitHub...</div>;
}

export default function Page() {
  return (
    <Suspense fallback={<div className="p-10 text-center animate-pulse text-text-muted">Loading...</div>}>
      <GitHubCallbackHandler />
    </Suspense>
  );
}
