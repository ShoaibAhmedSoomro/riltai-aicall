"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { verifyEmailApiV1AuthVerifyEmailPost } from "@/client/sdk.gen";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

type State =
  | { kind: "working" }
  | { kind: "verified" }
  | { kind: "rejected"; reason: string };

/**
 * Opening the link IS the action, so this posts on arrival rather than asking
 * the reader to press a second button after already clicking one in their
 * inbox.
 *
 * That is safe because verifying is idempotent on the server: a mail scanner
 * that loads the page in a headless browser, or React running the effect twice
 * in development, just reports the same success. The ref still guards against
 * the double fire so the second request is not sent at all.
 *
 * "Expired or invalid" gets a way forward, not a dead end. The resend lives in
 * Settings because it needs a signed-in user, so this links there.
 */
export function VerifyEmail() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<State>(
    token
      ? { kind: "working" }
      : { kind: "rejected", reason: "This page needs the link from your email." },
  );
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;

    verifyEmailApiV1AuthVerifyEmailPost({ body: { token } })
      .then((res) => {
        if (res.error) {
          setState({
            kind: "rejected",
            reason: detailFromError(res.error, "This link is not valid."),
          });
        } else {
          setState({ kind: "verified" });
        }
      })
      .catch(() =>
        setState({
          kind: "rejected",
          reason: "Something went wrong. Please try the link again.",
        }),
      );
  }, [token]);

  return (
    <AuthShell>
      {state.kind === "working" && (
        <div className="space-y-1.5 text-center" role="status">
          <h1 className="text-2xl font-semibold tracking-tight">
            Confirming your email…
          </h1>
          <p className="text-sm text-muted-foreground">One moment.</p>
        </div>
      )}

      {state.kind === "verified" && (
        <>
          <div className="space-y-1.5 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              Email confirmed
            </h1>
            <p className="text-sm text-muted-foreground">
              Thanks. This address is now verified on your account.
            </p>
          </div>
          <Button asChild className="w-full">
            <Link href="/after-sign-in">Continue to AICall</Link>
          </Button>
        </>
      )}

      {state.kind === "rejected" && (
        <>
          <div className="space-y-1.5 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              We couldn&apos;t confirm that
            </h1>
            <p className="text-sm text-muted-foreground">{state.reason}</p>
          </div>
          <p className="text-center text-sm text-muted-foreground">
            Sign in and request a fresh link from{" "}
            <Link
              href="/settings"
              className="text-primary underline-offset-4 hover:underline"
            >
              Settings
            </Link>
            .
          </p>
        </>
      )}
    </AuthShell>
  );
}
