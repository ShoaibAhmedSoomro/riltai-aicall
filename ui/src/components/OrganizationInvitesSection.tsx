"use client";

import { Info, Loader2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  createInviteApiV1OrganizationsInvitesPost,
  listInvitesApiV1OrganizationsInvitesGet,
  revokeInviteApiV1OrganizationsInvitesInviteIdDelete,
} from "@/client/sdk.gen";
import type { OrganizationInviteResponse, OrgRole } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

function formatExpiry(iso?: string | null): string {
  if (!iso) return "—";
  const days = Math.ceil(
    (new Date(iso).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  );
  if (days < 0) return "Expired";
  if (days === 0) return "Expires today";
  return `Expires in ${days} day${days === 1 ? "" : "s"}`;
}

export function OrganizationInvitesSection() {
  const { user, loading: authLoading } = useAuth();
  const hasFetched = useRef(false);

  const [invites, setInvites] = useState<OrganizationInviteResponse[]>([]);
  const [loading, setLoading] = useState(true);
  // The list endpoint is admin-only, so a 403 is how a member learns that --
  // no second request needed to find out what role they hold.
  const [adminOnly, setAdminOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  useEffect(() => {
    if (authLoading || !user || hasFetched.current) return;
    hasFetched.current = true;
    void fetchInvites();
  }, [authLoading, user]);

  async function fetchInvites() {
    setLoading(true);
    try {
      const response = await listInvitesApiV1OrganizationsInvitesGet();
      if (response.error) {
        if (response.response?.status === 403) {
          setAdminOnly(true);
          return;
        }
        setError(detailFromError(response.error, "Failed to load invitations"));
        return;
      }
      setInvites(response.data ?? []);
      setError(null);
    } catch (e) {
      setError(detailFromError(e, "Failed to load invitations"));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setCreating(true);
    try {
      const response = await createInviteApiV1OrganizationsInvitesPost({
        body: { email: email.trim(), role },
      });
      if (response.error) {
        // The server's refusals name the problem -- already a member, already
        // invited -- so show them rather than a generic failure.
        toast.error(detailFromError(response.error, "Could not create invitation"));
        return;
      }
      if (response.data) setInvites((prev) => [response.data!, ...prev]);
      setEmail("");
      setRole("member");
      toast.success("Invitation recorded");
    } catch (err) {
      toast.error(detailFromError(err, "Could not create invitation"));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(invite: OrganizationInviteResponse) {
    setRevokingId(invite.id);
    try {
      const response =
        await revokeInviteApiV1OrganizationsInvitesInviteIdDelete({
          path: { invite_id: invite.id },
        });
      if (response.error) {
        toast.error(detailFromError(response.error, "Could not revoke"));
        return;
      }
      setInvites((prev) => prev.filter((i) => i.id !== invite.id));
      toast.success(`Invitation to ${invite.email} withdrawn`);
    } catch (err) {
      toast.error(detailFromError(err, "Could not revoke"));
    } finally {
      setRevokingId(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading invitations…
      </div>
    );
  }

  if (adminOnly) {
    return (
      <p className="text-sm text-muted-foreground">
        Only an admin can invite people to this organization.
      </p>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="space-y-5">
      {/* Stated plainly and first. Without this an admin creates invitations and
          waits for people who were never contacted. */}
      <div className="flex gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          <span className="font-medium text-foreground">
            Invitations are recorded but not yet delivered.
          </span>{" "}
          This deployment has no email configured, so nothing is sent and an
          invitation cannot be accepted yet. Creating one now reserves the
          address and the role; they will be sendable once email is set up.
        </p>
      </div>

      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px] space-y-1.5">
          <Label htmlFor="invite-email">Email address</Label>
          <Input
            id="invite-email"
            type="email"
            required
            placeholder="colleague@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="w-[150px] space-y-1.5">
          <Label htmlFor="invite-role">Role</Label>
          <Select value={role} onValueChange={(v) => setRole(v as OrgRole)}>
            <SelectTrigger id="invite-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={creating || !email.trim()}>
          {creating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Create invitation
        </Button>
      </form>

      {invites.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No pending invitations.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invited</TableHead>
              <TableHead className="w-[110px]">Role</TableHead>
              <TableHead className="w-[150px]">Status</TableHead>
              <TableHead className="w-[60px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {invites.map((invite) => (
              <TableRow key={invite.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="font-medium">{invite.email}</span>
                    {invite.invited_by_email && (
                      <span className="text-xs text-muted-foreground">
                        by {invite.invited_by_email}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="capitalize">{invite.role}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatExpiry(invite.expires_at)}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Withdraw invitation to ${invite.email}`}
                    disabled={revokingId === invite.id}
                    onClick={() => void handleRevoke(invite)}
                  >
                    {revokingId === invite.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
