import {
  AudioLines,
  Brain,
  CircleDollarSign,
  Database,
  FileText,
  History,
  Home,
  Key,
  type LucideIcon,
  Megaphone,
  MessageSquare,
  Phone,
  PhoneIncoming,
  Settings,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";

/**
 * The sidebar's contents, kept apart from the component so the rules about it can
 * be tested without rendering the app.
 *
 * Grouped by what a person is doing: build an agent, put it on a phone line, look
 * at what happened, watch the numbers, manage the account. Labels describe the
 * page ("Audio Clips" are pre-recorded speech; "Recordings" read as call history),
 * and the rule for every entry is that it leads somewhere that works.
 */
export type SidebarNavItem = {
  title: string;
  /** Path, optionally with the query the page needs (`/usage?channel=chat`). */
  url: string;
  icon: LucideIcon;
  showsTelephonyWarning?: boolean;
};

export type SidebarNavSection = {
  label?: string;
  items: SidebarNavItem[];
};

export const NAV_SECTIONS: SidebarNavSection[] = [
  {
    items: [{ title: "Overview", url: "/overview", icon: Home }],
  },
  {
    label: "BUILD",
    items: [
      { title: "Agents", url: "/workflow", icon: Workflow },
      { title: "Knowledge Base", url: "/files", icon: Database },
      { title: "Audio Clips", url: "/recordings", icon: AudioLines },
      { title: "Tools", url: "/tools", icon: Wrench },
      { title: "Models", url: "/model-configurations", icon: Brain },
    ],
  },
  {
    label: "DEPLOY",
    items: [
      { title: "Phone Numbers", url: "/phone-numbers", icon: PhoneIncoming },
      {
        title: "Telephony",
        url: "/telephony-configurations",
        icon: Phone,
        showsTelephonyWarning: true,
      },
      { title: "Contacts", url: "/contacts", icon: Users },
      { title: "Campaigns", url: "/campaigns", icon: Megaphone },
    ],
  },
  {
    label: "DATA",
    items: [
      { title: "Call History", url: "/usage", icon: History },
      { title: "Chat History", url: "/usage?channel=chat", icon: MessageSquare },
    ],
  },
  {
    label: "MONITOR",
    items: [{ title: "Reports", url: "/reports", icon: FileText }],
  },
  {
    label: "ACCOUNT",
    items: [
      { title: "Developers", url: "/api-keys", icon: Key },
      { title: "Billing", url: "/billing", icon: CircleDollarSign },
      { title: "Settings", url: "/settings", icon: Settings },
    ],
  },
];

function parseUrl(url: string): { path: string; query: [string, string][] } {
  const [path, search = ""] = url.split("?");
  return { path, query: [...new URLSearchParams(search).entries()] };
}

function pathMatches(pathname: string, path: string): boolean {
  // A segment boundary, so "/workflow" owns "/workflow/12" but not "/workflow-x".
  return pathname === path || pathname.startsWith(`${path}/`);
}

/**
 * The one item that is active for this location, or null.
 *
 * An item is a candidate when the path is inside its path AND every query pair in
 * its url is present. Two items can share a path (Call History and Chat History
 * are both /usage), so the most specific candidate wins: more required query pairs
 * first, then the longer path. That is what lights only Chat History at
 * `/usage?channel=chat` and only Call History at `/usage`, where a plain
 * `pathname.startsWith` would light both.
 */
export function findActiveNavItem(
  sections: SidebarNavSection[],
  pathname: string,
  search: URLSearchParams | string,
): SidebarNavItem | null {
  const params = typeof search === "string" ? new URLSearchParams(search) : search;
  let best: { item: SidebarNavItem; score: [number, number] } | null = null;

  for (const section of sections) {
    for (const item of section.items) {
      const { path, query } = parseUrl(item.url);
      if (!pathMatches(pathname, path)) continue;
      if (!query.every(([k, v]) => params.get(k) === v)) continue;
      const score: [number, number] = [query.length, path.length];
      if (!best || score[0] > best.score[0] || (score[0] === best.score[0] && score[1] > best.score[1])) {
        best = { item, score };
      }
    }
  }
  return best?.item ?? null;
}
