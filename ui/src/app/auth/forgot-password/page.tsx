"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { forgotPasswordApiV1AuthForgotPasswordPost } from "@/client/sdk.gen";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

/**
 * The page shows the SAME confirmation whether or not the address has an
 * account, because the endpoint deliberately answers the same way: this is
 * reachable without signing in, so distinguishing the two turns it into a way
 * to ask whether a given person is a customer.
 *
 * The one thing it does surface is the 503 the backend returns when email is
 * not configured on the deployment. That is a fact about the server, not about
 * any user, and swallowing it would leave the reader waiting for a message
 * that was never going to be sent.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setUnavailable(null);

    try {
      const res = await forgotPasswordApiV1AuthForgotPasswordPost({
        body: { email },
      });

      if (res.error) {
        const detail = detailFromError(res.error, "Could not start a password reset.");
        // 503 is the deployment saying it cannot send mail at all. Anything
        // else is shown as an error rather than a false confirmation.
        if (res.response?.status === 503) {
          setUnavailable(detail);
        } else {
          toast.error(detail);
        }
        return;
      }

      setSent(true);
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <AuthShell>
        <div className="space-y-1.5 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Check your email</h1>
          <p className="text-sm text-muted-foreground">
            If an account exists for {email}, a reset link is on its way. It stops
            working in 30 minutes, and as soon as it is used once.
          </p>
        </div>
        <p className="text-center text-sm text-muted-foreground">
          <Link href="/auth/login" className="text-primary underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Reset your password</h1>
        <p className="text-sm text-muted-foreground">
          We&apos;ll email you a link to choose a new one
        </p>
      </div>

      {unavailable && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
          {unavailable}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Sending..." : "Send reset link"}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        <Link href="/auth/login" className="text-primary underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}
