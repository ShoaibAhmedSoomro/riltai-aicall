"use client";

import { AlertTriangle, PanelLeftClose, PanelLeftOpen, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import React, { type ReactNode, Suspense } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { SidebarTeamSwitcher } from "@/components/layout/SidebarTeamSwitcher";
import ThemeToggle from "@/components/ThemeSwitcher";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLeadForms } from "@/context/LeadFormsContext";
import { useTelephonyConfigWarnings } from "@/context/TelephonyConfigWarningsContext";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

import { findActiveNavItem, NAV_SECTIONS, type SidebarNavItem } from "./navConfig";

const TELEPHONY_WARNING_COPY = "Action required";

/**
 * Reads the query string, which needs a Suspense boundary. The fallback renders the
 * same children with no query, so the sidebar is never blank while it resolves.
 */
function WithSearchParams({ children }: { children: (search: URLSearchParams) => ReactNode }) {
  return <>{children(useSearchParams())}</>;
}

export function AppSidebar() {
  const pathname = usePathname();
  const { state, isMobile, setOpenMobile } = useSidebar();
  const { provider } = useAuth();
  const { openHireExpert } = useLeadForms();
  const {
    telnyxMissingWebhookPublicKeyCount,
    vonageMissingSignatureSecretCount,
  } = useTelephonyConfigWarnings();
  const hasTelephonyWarning =
    telnyxMissingWebhookPublicKeyCount > 0 ||
    vonageMissingSignatureSecretCount > 0;
  const isCollapsed = !isMobile && state === "collapsed";


  const handleMobileNavClick = () => {
    if (isMobile) {
      setOpenMobile(false);
    }
  };

  const SidebarLink = ({ item, active }: { item: SidebarNavItem; active: boolean }) => {
    const isItemActive = active;
    const Icon = item.icon;
    const showWarningDot = item.showsTelephonyWarning && hasTelephonyWarning;
    const tooltip = {
      children: (
        <div className="notranslate" translate="no">
          <p>{item.title}</p>
          {showWarningDot && (
            <p className="text-amber-600 dark:text-amber-400">{TELEPHONY_WARNING_COPY}</p>
          )}
        </div>
      ),
    };
    const warningIndicator = (
      <AlertTriangle
        aria-label="Action required on a telephony configuration"
        className={cn(
          "text-amber-500",
          isCollapsed ? "absolute -right-0.5 -top-0.5 h-3 w-3" : "ml-auto h-3.5 w-3.5"
        )}
      />
    );

    return (
      <SidebarMenuButton
        asChild
        tooltip={tooltip}
        className={cn(
          "rounded-md transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
          isItemActive &&
            "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
        )}
      >
        <Link
          href={item.url}
          aria-current={isItemActive ? "page" : undefined}
          onClick={handleMobileNavClick}
          className={cn("relative", isCollapsed && "justify-center")}
          translate="no"
        >
          {isItemActive && !isCollapsed && (
            <span
              className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-sidebar-ring"
              aria-hidden
            />
          )}
          <Icon
            className={cn(
              "h-4 w-4 shrink-0",
              isItemActive && "text-sidebar-ring"
            )}
          />
          <span
            className={cn("notranslate min-w-0 flex-1 truncate", isCollapsed && "sr-only")}
            translate="no"
          >
            {item.title}
          </span>
          {showWarningDot && (
            isCollapsed ? (
              warningIndicator
            ) : (
              <Tooltip>
                <TooltipTrigger asChild>
                  {warningIndicator}
                </TooltipTrigger>
                <TooltipContent side="right">
                  <p>{TELEPHONY_WARNING_COPY}</p>
                </TooltipContent>
              </Tooltip>
            )
          )}
        </Link>
      </SidebarMenuButton>
    );
  };

  // One item is lit, worked out from path AND query (see navConfig).
  const renderNav = (search: URLSearchParams) => {
    const activeUrl = findActiveNavItem(NAV_SECTIONS, pathname, search)?.url;
    return NAV_SECTIONS.map((section, index) => (
      <SidebarGroup
        key={section.label ?? "overview"}
        className={index === 0 ? "mt-2" : "mt-6"}
      >
        {section.label && (
          <SidebarGroupLabel
            className={cn(
              "notranslate text-xs font-semibold uppercase tracking-wider text-muted-foreground",
              isCollapsed && "hidden"
            )}
            translate="no"
          >
            {section.label}
          </SidebarGroupLabel>
        )}
        <SidebarMenu>
          {section.items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarLink item={item} active={item.url === activeUrl} />
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroup>
    ));
  };

  // "Hire an Expert" CTA, rendered INSIDE the shared footer pill next to the
  // profile icon. Expanded: label pill filling the row. Collapsed: icon-only.
  const hireExpertButton = isCollapsed ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          size="icon"
          className="h-7 w-7 rounded-md"
          onClick={() => openHireExpert("sidebar")}
          aria-label="Hire an Expert"
        >
          <UserRound className="h-3.5 w-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">
        <p>Hire an Expert</p>
      </TooltipContent>
    </Tooltip>
  ) : (
    <Button
      size="sm"
      className="h-7 gap-1.5 px-3 text-xs"
      onClick={() => openHireExpert("sidebar")}
    >
      <UserRound className="h-3.5 w-3.5" />
      Hire an Expert
    </Button>
  );

  return (
    <Sidebar collapsible="icon" variant="sidebar">
      <SidebarHeader className="px-2 py-3 notranslate" translate="no">
        <div className={cn("flex items-center justify-between", isCollapsed && "flex-col gap-2")}>
          <Link
            href="/"
            className="notranslate flex items-center gap-2 px-1"
            translate="no"
            aria-label="AICall home"
          >
            <BrandLogo mark className="h-6" />
          </Link>

          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger className="hover:bg-accent">
                {isCollapsed ? (
                  <PanelLeftOpen className="h-4 w-4" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" />
                )}
              </SidebarTrigger>
            </TooltipTrigger>
            <TooltipContent side={isCollapsed ? "right" : "bottom"}>
              <p>{isCollapsed ? "Expand" : "Collapse"} sidebar (Ctrl+B)</p>
            </TooltipContent>
          </Tooltip>
        </div>

        {provider === "stack" && (
          <div className={cn("mt-3 notranslate", isCollapsed && "hidden")} translate="no">
            <SidebarTeamSwitcher />
          </div>
        )}
      </SidebarHeader>

      <SidebarContent className={cn("notranslate", isCollapsed && "px-0")} translate="no">
        <Suspense fallback={renderNav(new URLSearchParams())}>
          <WithSearchParams>{renderNav}</WithSearchParams>
        </Suspense>
      </SidebarContent>

      <SidebarFooter
        className={cn("p-3 notranslate", isCollapsed && "p-2")}
        translate="no"
      >
        <div className="space-y-2">
          {/* Name, email, settings and sign out live in the header's account menu
              (ProfileMenu). This footer used to repeat all of it twice. */}
          <div className={cn("flex", isCollapsed ? "justify-center" : "justify-start")}>
            {hireExpertButton}
          </div>

          <div className="mt-1 flex justify-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="notranslate" translate="no">
                  <ThemeToggle
                    showLabel={false}
                    className="rounded-md hover:bg-accent hover:text-accent-foreground"
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent side={isCollapsed ? "right" : "top"}>
                <p>Toggle theme</p>
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
