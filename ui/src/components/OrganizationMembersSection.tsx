"use client";

import { Loader2, ShieldCheck, UserMinus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  listMembersApiV1OrganizationsMembersGet,
  removeMemberApiV1OrganizationsMembersUserIdDelete,
  updateMemberRoleApiV1OrganizationsMembersUserIdPatch,
} from "@/client/sdk.gen";
import type { OrganizationMemberResponse, OrgRole } from "@/client/types.gen";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

const ROLE_LABEL: Record<OrgRole, string> = {
  admin: "Admin",
  member: "Member",
};

const ROLE_HELP: Record<OrgRole, string> = {
  admin: "Can change billing, credentials, phone numbers and member roles.",
  member: "Can build agents and run calls, but not change org-wide settings.",
};

function displayName(m: OrganizationMemberResponse): string {
  return m.name?.trim() || m.email || `User ${m.user_id}`;
}

export function OrganizationMembersSection() {
  const { user, loading: authLoading, logout } = useAuth();
  const hasFetched = useRef(false);

  const [members, setMembers] = useState<OrganizationMemberResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Demoting yourself is a one-way door for you personally: you lose the very
  // control that would put it back. Worth a confirmation rather than a silent
  // select change.
  const [pendingSelfDemotion, setPendingSelfDemotion] = useState<OrgRole | null>(
    null,
  );
  const [pendingRemoval, setPendingRemoval] =
    useState<OrganizationMemberResponse | null>(null);

  useEffect(() => {
    if (authLoading || !user || hasFetched.current) {
      return;
    }
    hasFetched.current = true;
    void fetchMembers();
  }, [authLoading, user]);

  async function fetchMembers() {
    setLoading(true);
    try {
      const response = await listMembersApiV1OrganizationsMembersGet();
      // The generated client resolves on HTTP errors rather than throwing, so
      // response.error has to be checked or a failure reads as an empty org.
      if (response.error) {
        setError(detailFromError(response.error, "Failed to load members"));
        return;
      }
      setMembers(response.data ?? []);
      setError(null);
    } catch (e) {
      setError(detailFromError(e, "Failed to load members"));
    } finally {
      setLoading(false);
    }
  }

  async function applyRole(member: OrganizationMemberResponse, role: OrgRole) {
    setSavingId(member.user_id);
    try {
      const response =
        await updateMemberRoleApiV1OrganizationsMembersUserIdPatch({
          path: { user_id: member.user_id },
          body: { role },
        });
      if (response.error) {
        // The server's refusals are written to be read by a person -- notably
        // the last-admin guard -- so surface them rather than a generic string.
        toast.error(detailFromError(response.error, "Could not change role"));
        return;
      }
      setMembers((prev) =>
        prev.map((m) => (m.user_id === member.user_id ? { ...m, role } : m)),
      );
      toast.success(`${displayName(member)} is now ${ROLE_LABEL[role]}`);
    } catch (e) {
      toast.error(detailFromError(e, "Could not change role"));
    } finally {
      setSavingId(null);
    }
  }

  async function removeMember(member: OrganizationMemberResponse) {
    setSavingId(member.user_id);
    try {
      const response = await removeMemberApiV1OrganizationsMembersUserIdDelete({
        path: { user_id: member.user_id },
      });
      if (response.error) {
        // Carries the last-admin refusal, which names what to do instead.
        toast.error(detailFromError(response.error, "Could not remove"));
        return;
      }
      if (member.is_self) {
        // Leaving clears the selected organization server-side, so this session
        // no longer resolves one and every org-scoped screen would 400. Sign
        // out rather than leave them clicking around a broken app.
        toast.success("You have left the organization");
        await logout();
        return;
      }
      setMembers((prev) => prev.filter((m) => m.user_id !== member.user_id));
      toast.success(`${displayName(member)} was removed`);
    } catch (e) {
      toast.error(detailFromError(e, "Could not remove"));
    } finally {
      setSavingId(null);
    }
  }

  // Derived from the list rather than from the session: the user endpoint does
  // not carry an org role, and this row is authoritative for the selected org.
  const me = members.find((m) => m.is_self);
  const iAmAdmin = me?.role === "admin" || Boolean(me?.is_superuser);
  const adminCount = members.filter((m) => m.role === "admin").length;

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading members…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead className="w-[180px]">Role</TableHead>
            <TableHead className="w-[60px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((member) => {
            const isOnlyAdmin = member.role === "admin" && adminCount <= 1;
            // An admin may remove anyone; anyone at all may remove themselves.
            // Mirrors the handler, which is deliberately not require_admin-gated
            // so that a member can leave without an admin doing it for them.
            const canRemove = iAmAdmin || member.is_self;
            return (
              <TableRow key={member.user_id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="flex items-center gap-2 font-medium">
                      {displayName(member)}
                      {member.is_self && (
                        <Badge variant="outline" className="font-normal">
                          You
                        </Badge>
                      )}
                      {member.is_superuser && (
                        <Badge
                          variant="secondary"
                          className="flex items-center gap-1 font-normal"
                        >
                          <ShieldCheck className="h-3 w-3" />
                          SuperAdmin
                        </Badge>
                      )}
                    </span>
                    {member.email && member.name && (
                      <span className="text-xs text-muted-foreground">
                        {member.email}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  {iAmAdmin ? (
                    <Select
                      value={member.role}
                      disabled={savingId === member.user_id || isOnlyAdmin}
                      onValueChange={(next) => {
                        const role = next as OrgRole;
                        if (role === member.role) return;
                        if (member.is_self && role !== "admin") {
                          setPendingSelfDemotion(role);
                          return;
                        }
                        void applyRole(member, role);
                      }}
                    >
                      <SelectTrigger className="w-[150px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">Admin</SelectItem>
                        <SelectItem value="member">Member</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Badge variant="secondary" className="font-normal">
                      {ROLE_LABEL[member.role as OrgRole] ?? member.role}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  {canRemove && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      disabled={savingId === member.user_id || isOnlyAdmin}
                      // Named rather than icon-only: with one of these on every
                      // row, "button" alone identifies nothing to a screen
                      // reader, and this one is destructive.
                      aria-label={
                        member.is_self
                          ? "Leave this organization"
                          : `Remove ${displayName(member)}`
                      }
                      title={
                        isOnlyAdmin
                          ? "The only admin cannot be removed"
                          : undefined
                      }
                      onClick={() => setPendingRemoval(member)}
                    >
                      <UserMinus className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <div className="space-y-1 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Admin.</span>{" "}
          {ROLE_HELP.admin}
        </p>
        <p>
          <span className="font-medium text-foreground">Member.</span>{" "}
          {ROLE_HELP.member}
        </p>
        {iAmAdmin && adminCount <= 1 && (
          <p>
            This organization has one admin, so that role cannot be changed and
            that person cannot be removed. Promote someone else first.
          </p>
        )}
        {!iAmAdmin && (
          <p>
            Only an admin can change roles or remove other people. You can still
            leave the organization yourself.
          </p>
        )}
      </div>

      <AlertDialog
        open={pendingSelfDemotion !== null}
        onOpenChange={(open) => !open && setPendingSelfDemotion(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Give up your admin access?</AlertDialogTitle>
            <AlertDialogDescription>
              You will no longer be able to change billing, credentials, phone
              numbers or member roles — including this one. Another admin will
              have to restore it for you.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const role = pendingSelfDemotion;
                setPendingSelfDemotion(null);
                if (me && role) void applyRole(me, role);
              }}
            >
              Yes, make me a member
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => !open && setPendingRemoval(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingRemoval?.is_self
                ? "Leave this organization?"
                : `Remove ${pendingRemoval ? displayName(pendingRemoval) : ""}?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval?.is_self
                ? "You will be signed out and will lose access to this organization's agents, calls and settings. An admin has to invite you back. Everything you built stays with the organization."
                : "They lose access immediately. The agents, campaigns and calls they created stay with the organization. If they know an API key, that key belongs to the organization and keeps working until you rotate it."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const member = pendingRemoval;
                setPendingRemoval(null);
                if (member) void removeMember(member);
              }}
            >
              {pendingRemoval?.is_self ? "Yes, leave" : "Yes, remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
