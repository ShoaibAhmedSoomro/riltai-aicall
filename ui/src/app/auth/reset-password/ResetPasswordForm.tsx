"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { resetPasswordApiV1AuthResetPasswordPost } from "@/client/sdk.gen";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

/**
 * Finishing a reset signs the user straight in, which is why this sets the
 * session cookie exactly the way LoginForm does. The alternative sends
 * someone who just proved control of the mailbox back to a login form to
 * retype the password they chose ten seconds ago.
 *
 * The token is single use and expires in 30 minutes, so "expired or already
 * used" is a normal outcome, not an error state -- it gets a route back to
 * requesting a fresh one rather than a bare toast.
 */
export function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Checked here rather than server-side: the server has no second field to
    // compare against, and a mismatch is a typo, not a security condition.
    if (password !== confirm) {
      toast.error("Those two passwords do not match.");
      return;
    }

    setLoading(true);
    setRejected(null);

    try {
      const res = await resetPasswordApiV1AuthResetPasswordPost({
        body: { token, password },
      });

      if (res.error || !res.data) {
        setRejected(
          detailFromError(res.error, "This reset link is not valid."),
        );
        return;
      }

      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: res.data.token, user: res.data.user }),
      });

      window.location.href = "/after-sign-in";
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <AuthShell>
        <div className="space-y-1.5 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Link incomplete</h1>
          <p className="text-sm text-muted-foreground">
            This page needs the link from your email. Request a new one and open
            it directly.
          </p>
        </div>
        <Button asChild className="w-full">
          <Link href="/auth/forgot-password">Request a new link</Link>
        </Button>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Choose a new password</h1>
        <p className="text-sm text-muted-foreground">
          You&apos;ll be signed in once it&apos;s saved
        </p>
      </div>

      {rejected && (
        <div className="space-y-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
          <p>{rejected}</p>
          <Link
            href="/auth/forgot-password"
            className="inline-block font-medium underline underline-offset-4"
          >
            Request a new link
          </Link>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">New password</Label>
          <Input
            id="password"
            type="password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">Confirm password</Label>
          <Input
            id="confirm"
            type="password"
            placeholder="Type it again"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Saving..." : "Save and sign in"}
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
