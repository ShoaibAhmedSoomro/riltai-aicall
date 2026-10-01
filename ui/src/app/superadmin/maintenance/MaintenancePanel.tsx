"use client";

import { CheckCircle2, HardDrive, Loader2, Trash2, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getMaintenanceStatusApiV1SuperuserMaintenanceGet,
  requestBuildCachePruneApiV1SuperuserMaintenancePruneBuildCachePost,
} from "@/client/sdk.gen";
import type { MaintenanceStatusResponse } from "@/client/types.gen";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

/** Docker prints decimal units, and so does the host script, so this does too. */
export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let value = n;
  let i = -1;
  do {
    value /= 1000;
    i += 1;
  } while (value >= 1000 && i < units.length - 1);
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[i]}`;
}

const SOURCE_LABEL: Record<string, string> = {
  manual: "Cleared from this page",
  auto: "Weekly automatic clean-up",
  "auto-emergency": "Automatic clean-up (disk nearly full)",
};

const POLL_MS = 4000;
// The host checks for a request once a minute, so allow a little over that.
const GIVE_UP_AFTER_MS = 3 * 60 * 1000;

/**
 * Disk usage and a button to clear the Docker build cache.
 *
 * Three states are kept deliberately apart, because they mean different things:
 *   - the host has not reported a cache size yet  -> "Not reported yet", NOT 0 B
 *   - a clean-up ran and freed nothing            -> "0 B"
 *   - a clean-up failed                           -> the error, in plain view
 * Rendering the first as 0 would tell an operator with a 100 GB cache that it
 * is empty.
 *
 * The button only files a request; the server picks it up within a minute. So
 * pressing it is not the same as it having happened, and the panel polls until
 * the host reports a newer clean-up rather than claiming success on the click.
 */
export function MaintenancePanel() {
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<MaintenanceStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waitingFor, setWaitingFor] = useState<{
    baseline: string | null;
    since: number;
  } | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const waitingRef = useRef(waitingFor);
  waitingRef.current = waitingFor;

  const load = useCallback(async () => {
    const res = await getMaintenanceStatusApiV1SuperuserMaintenanceGet();
    if (res.error || !res.data) {
      setError(
        detailFromError(res.error, "Could not load server maintenance status."),
      );
      return;
    }
    setError(null);
    setStatus(res.data);

    const waiting = waitingRef.current;
    if (!waiting) return;
    if ((res.data.last_prune?.at ?? null) !== waiting.baseline) {
      // The host reported a clean-up newer than the one we started from.
      setWaitingFor(null);
      setTimedOut(false);
      if (res.data.last_prune?.ok) toast.success("Build cache cleared");
      else toast.error("The clean-up failed. Details are on this page.");
    } else if (Date.now() - waiting.since > GIVE_UP_AFTER_MS) {
      setWaitingFor(null);
      setTimedOut(true);
    }
  }, []);

  // The auth interceptor that attaches the bearer token is only registered once
  // auth has finished loading. Fetching earlier sends an unauthenticated request
  // that fails silently -- here as a "superuser required" error for someone who
  // is one.
  useEffect(() => {
    if (authLoading || !user) return;
    load();
  }, [authLoading, user, load]);

  useEffect(() => {
    if (!waitingFor) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [waitingFor, load]);

  async function handleClear() {
    setSubmitting(true);
    setTimedOut(false);
    try {
      const res =
        await requestBuildCachePruneApiV1SuperuserMaintenancePruneBuildCachePost();
      if (res.error) {
        toast.error(detailFromError(res.error, "Could not request the clean-up."));
        return;
      }
      setWaitingFor({
        baseline: status?.last_prune?.at ?? null,
        since: Date.now(),
      });
    } catch (err) {
      toast.error(detailFromError(err, "Could not request the clean-up."));
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!status) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const pending = status.prune_requested || waitingFor !== null;
  const threshold = status.policy?.emergency_disk_percent ?? 85;
  const diskHigh = status.disk.percent >= threshold;
  const last = status.last_prune;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" /> Server disk
          </CardTitle>
          <CardDescription>
            The disk the whole platform runs on, including recordings and the
            database.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div
            role="progressbar"
            aria-valuenow={Math.round(status.disk.percent)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Disk used"
            className="h-3 w-full overflow-hidden rounded-full bg-muted"
          >
            <div
              className={`h-full rounded-full ${diskHigh ? "bg-destructive" : "bg-foreground"}`}
              style={{ width: `${Math.min(100, status.disk.percent)}%` }}
            />
          </div>
          <p className="text-sm">
            <span className="font-medium">{formatBytes(status.disk.used_bytes)}</span>{" "}
            of {formatBytes(status.disk.total_bytes)} used ({status.disk.percent}%)
            {diskHigh && (
              <span className="ml-2 font-medium text-destructive">
                Nearly full
              </span>
            )}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Docker build cache</CardTitle>
          <CardDescription>
            Leftovers from building the app. Safe to delete: it is only ever a
            speed-up, and it is rebuilt when needed. Images, containers and the
            database are never touched.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Size right now</dt>
              <dd className="text-lg font-semibold">
                {status.build_cache_bytes === null ||
                status.build_cache_bytes === undefined
                  ? "Not reported yet"
                  : formatBytes(status.build_cache_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last clean-up</dt>
              <dd className="font-medium">
                {last ? (
                  <span className="flex items-center gap-1.5">
                    {last.ok ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <XCircle className="h-4 w-4 text-destructive" />
                    )}
                    {new Date(last.at).toLocaleString()}
                  </span>
                ) : (
                  "None yet"
                )}
              </dd>
              {last && (
                <dd className="text-xs text-muted-foreground">
                  {SOURCE_LABEL[last.source] ?? last.source}
                  {last.ok && last.freed_bytes !== null && last.freed_bytes !== undefined
                    ? ` · freed ${formatBytes(last.freed_bytes)}`
                    : ""}
                </dd>
              )}
            </div>
          </dl>

          {last && !last.ok && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
              <p className="font-medium text-destructive">The last clean-up failed</p>
              <p className="mt-1 break-words text-muted-foreground">
                {last.error ?? "No details were reported."}
              </p>
            </div>
          )}

          {!status.available ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
              Server maintenance isn&apos;t available on this deployment: the
              shared maintenance folder isn&apos;t mounted, so a request from
              here could never be picked up.
            </p>
          ) : (
            <div className="space-y-2">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button disabled={pending || submitting}>
                    {pending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Waiting for the server…
                      </>
                    ) : (
                      <>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Clear build cache now
                      </>
                    )}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Clear the whole build cache?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This frees the space straight away. The next deploy will
                      take longer, because it has to rebuild what was cached.
                      Nothing running is affected, and no data is deleted.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={handleClear}>
                      Clear it
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

              {pending && (
                <p className="text-xs text-muted-foreground">
                  Requested. The server checks once a minute, so this can take up
                  to about a minute.
                </p>
              )}
              {timedOut && (
                <p className="text-xs text-destructive">
                  Still no answer from the server. The request is filed; check
                  again shortly.
                </p>
              )}
            </div>
          )}

          <p className="text-xs text-muted-foreground">
            {status.policy
              ? `Automatic: every Sunday, anything older than ${Math.round(
                  status.policy.auto_keep_hours / 24,
                )} days is cleared. If the disk passes ${status.policy.emergency_disk_percent}%, all of it is.`
              : "Automatic clean-up is scheduled on the server; its policy will show here once the server has reported."}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
