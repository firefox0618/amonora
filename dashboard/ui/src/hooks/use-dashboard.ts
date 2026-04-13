"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import {
  AuditPayload,
  CampaignAnalyticsDetailPayload,
  CampaignAnalyticsPayload,
  KnowledgePayload,
  NotificationsPayload,
  OverviewPayload,
  PaymentsPayload,
  PromoCodesPayload,
  SearchPayload,
  ServersPayload,
  SessionPayload,
  SettingsPayload,
  SupportPayload,
  TrafficPayload,
  UserDetailPayload,
  UsersPayload,
} from "@/lib/types";


function foregroundRefetchInterval(intervalMs: number, enabled = true): number | false {
  if (!enabled) return false;
  if (typeof document === "undefined") return intervalMs;
  return document.visibilityState === "visible" && document.hasFocus() ? intervalMs : false;
}

const quietQueryDefaults = {
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
} as const;

export function useSession() {
  return useQuery({
    queryKey: ["session"],
    queryFn: () => apiGet<SessionPayload>("/session"),
    ...quietQueryDefaults,
    retry: false,
    staleTime: 60_000,
  });
}

export function useGlobalSearch(query: string) {
  return useQuery({
    queryKey: ["global-search", query],
    queryFn: () => apiGet<SearchPayload>(`/search?q=${encodeURIComponent(query)}`),
    ...quietQueryDefaults,
    enabled: query.trim().length >= 2,
    staleTime: 10_000,
  });
}

export function useNotifications(enabled = true) {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiGet<NotificationsPayload>("/notifications"),
    ...quietQueryDefaults,
    enabled,
    staleTime: 25_000,
    refetchInterval: () => foregroundRefetchInterval(30_000, enabled),
  });
}

export function useAudit(limit = 150) {
  return useQuery({
    queryKey: ["audit", limit],
    queryFn: () => apiGet<AuditPayload>(`/audit?limit=${limit}`),
    ...quietQueryDefaults,
    staleTime: 45_000,
    refetchInterval: () => foregroundRefetchInterval(60_000),
  });
}

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: () => apiGet<OverviewPayload>("/overview"),
    ...quietQueryDefaults,
    staleTime: 45_000,
    refetchInterval: () => foregroundRefetchInterval(45_000),
  });
}

export function useUsers({
  query,
  statusFilter = "all",
  planFilter = "all",
  issueFilter = "all",
  page = 1,
  pageSize = 100,
}: {
  query: string;
  statusFilter?: string;
  planFilter?: string;
  issueFilter?: string;
  page?: number;
  pageSize?: number;
}) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (planFilter !== "all") params.set("plan", planFilter);
  if (issueFilter !== "all") params.set("issue", issueFilter);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return useQuery({
    queryKey: ["users", query, statusFilter, planFilter, issueFilter, page, pageSize],
    queryFn: () => apiGet<UsersPayload>(`/users?${params.toString()}`),
    ...quietQueryDefaults,
    staleTime: 20_000,
    placeholderData: (previousData) => previousData,
  });
}

export function useUserDetail(userId?: number) {
  return useQuery({
    queryKey: ["user-detail", userId],
    queryFn: () => apiGet<UserDetailPayload>(`/users/${userId}`),
    ...quietQueryDefaults,
    enabled: Boolean(userId),
    staleTime: 30_000,
  });
}

export function useServers(serverId?: number, force = false) {
  const search = new URLSearchParams();
  if (serverId) search.set("server_id", String(serverId));
  if (force) search.set("force", "1");
  return useQuery({
    queryKey: ["servers", serverId, force],
    queryFn: () => apiGet<ServersPayload>(`/servers${search.toString() ? `?${search.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 45_000,
    refetchInterval: () => foregroundRefetchInterval(45_000),
  });
}

export function useTraffic() {
  return useQuery({
    queryKey: ["traffic"],
    queryFn: () => apiGet<TrafficPayload>("/traffic"),
    ...quietQueryDefaults,
    staleTime: 45_000,
    refetchInterval: () => foregroundRefetchInterval(45_000),
  });
}

export function usePayments(
  recordId?: number,
  periodKey?: string,
  query?: string,
  statusFilter = "all",
  methodFilter = "all",
  issueFilter = "all",
) {
  const params = new URLSearchParams();
  if (recordId) params.set("record_id", String(recordId));
  if (periodKey) params.set("period_key", periodKey);
  if ((query || "").trim()) params.set("q", String(query).trim());
  if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
  if (methodFilter && methodFilter !== "all") params.set("method", methodFilter);
  if (issueFilter && issueFilter !== "all") params.set("issue", issueFilter);
  return useQuery({
    queryKey: ["payments", recordId, periodKey, query || "", statusFilter, methodFilter, issueFilter],
    queryFn: () => apiGet<PaymentsPayload>(`/payments${params.toString() ? `?${params.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 15_000,
    refetchInterval: () => foregroundRefetchInterval(20_000),
  });
}

export function useCampaignAnalytics(
  query = "",
  options?: {
    periodKey?: string;
    dateFrom?: string;
    dateTo?: string;
  },
) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (options?.periodKey) params.set("period_key", options.periodKey);
  if (options?.dateFrom) params.set("date_from", options.dateFrom);
  if (options?.dateTo) params.set("date_to", options.dateTo);
  return useQuery({
    queryKey: ["analytics-campaigns", query, options?.periodKey || "", options?.dateFrom || "", options?.dateTo || ""],
    queryFn: () => apiGet<CampaignAnalyticsPayload>(`/analytics/campaigns${params.toString() ? `?${params.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 20_000,
    refetchInterval: () => foregroundRefetchInterval(30_000),
  });
}

export function useCampaignAnalyticsDetail(
  campaignId?: number,
  options?: {
    periodKey?: string;
    dateFrom?: string;
    dateTo?: string;
  },
) {
  const params = new URLSearchParams();
  if (options?.periodKey) params.set("period_key", options.periodKey);
  if (options?.dateFrom) params.set("date_from", options.dateFrom);
  if (options?.dateTo) params.set("date_to", options.dateTo);
  return useQuery({
    queryKey: ["analytics-campaign-detail", campaignId, options?.periodKey || "", options?.dateFrom || "", options?.dateTo || ""],
    queryFn: () =>
      apiGet<CampaignAnalyticsDetailPayload>(
        `/analytics/campaigns/${campaignId}${params.toString() ? `?${params.toString()}` : ""}`,
      ),
    ...quietQueryDefaults,
    enabled: Boolean(campaignId),
    staleTime: 20_000,
  });
}

export function usePromoCodes(query?: string, kindFilter = "all", statusFilter = "all") {
  const params = new URLSearchParams();
  if ((query || "").trim()) params.set("q", String(query).trim());
  if (kindFilter && kindFilter !== "all") params.set("kind", kindFilter);
  if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
  return useQuery({
    queryKey: ["promocodes", query || "", kindFilter, statusFilter],
    queryFn: () => apiGet<PromoCodesPayload>(`/promocodes${params.toString() ? `?${params.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 15_000,
    refetchInterval: () => foregroundRefetchInterval(20_000),
  });
}

export function useSupport(filterMode: string, query: string, ticketId?: number) {
  const search = new URLSearchParams();
  if (filterMode) search.set("filter_mode", filterMode);
  if (query) search.set("q", query);
  if (ticketId) search.set("ticket_id", String(ticketId));

  return useQuery({
    queryKey: ["support", filterMode, query, ticketId],
    queryFn: () => apiGet<SupportPayload>(`/support?${search.toString()}`),
    ...quietQueryDefaults,
    staleTime: 20_000,
    refetchInterval: () => foregroundRefetchInterval(30_000),
  });
}

export function useSettings(doc?: string) {
  const search = new URLSearchParams();
  if (doc) search.set("doc", doc);
  return useQuery({
    queryKey: ["settings", doc],
    queryFn: () => apiGet<SettingsPayload>(`/settings${search.toString() ? `?${search.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 60_000,
  });
}

export function useKnowledge(doc?: string) {
  const search = new URLSearchParams();
  if (doc) search.set("doc", doc);
  return useQuery({
    queryKey: ["knowledge", doc],
    queryFn: () => apiGet<KnowledgePayload>(`/knowledge${search.toString() ? `?${search.toString()}` : ""}`),
    ...quietQueryDefaults,
    staleTime: 60_000,
  });
}
