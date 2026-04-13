export type ApiEnvelope<T = unknown> = {
  ok: boolean;
  data: T;
  error?: string;
  notice?: string;
};

export type SessionPayload = {
  admin: {
    id: number;
    username: string;
    display_name: string;
    initials: string;
    role: string;
    role_name: string;
    telegram_id?: number | null;
    avatar_url?: string | null;
    last_login_at?: string | null;
    permissions: Record<string, boolean>;
  };
  settings: {
    title: string;
    cookie_name: string;
    session_hours: number;
    session_idle_minutes: number;
  };
  product: {
    name: string;
    title: string;
  };
  profile: {
    telegram_id?: number | null;
    avatar_url?: string | null;
    last_login_at?: string | null;
    session_idle_minutes: number;
    session_hours: number;
  };
  navigation: Array<{
    key: string;
    label: string;
    href: string;
  }>;
};

export type SearchPayload = {
  query: string;
  sections: Array<{
    key: string;
    label: string;
    items: Array<{
      id: string;
      title: string;
      subtitle: string;
      href: string;
      tag: string;
    }>;
  }>;
};

export type NotificationsPayload = {
  alerts: Array<{ title: string; text: string; href: string; action: string }>;
  recent_payments: PaymentRecord[];
  support_counts: Record<string, number>;
  unread: number;
  items: Array<{
    id: string;
    kind: string;
    title: string;
    text: string;
    href: string;
    meta?: string;
  }>;
};

export type AuditItem = {
  id: number;
  action: string;
  action_label?: string;
  target_type?: string | null;
  target_id?: string | null;
  details_text?: string | null;
  raw_details_text?: string | null;
  created_at: string;
  admin_name: string;
};

export type AuditPayload = {
  summary: {
    total: number;
    unique_actions: number;
    active_admins: number;
    target_types: number;
    latest_event_at: string;
  };
  items: AuditItem[];
  top_actions: Array<{ action: string; count: number }>;
  top_admins: Array<{ name: string; count: number }>;
  top_targets: Array<{ target_type: string; count: number }>;
};

export type OverviewPayload = {
  priority?: string;
  kpis: {
    total_users: number;
    active_users: number;
    paid_users?: number;
    trial_users?: number;
    active_connections: number;
    monthly_revenue: number;
    daily_revenue?: number;
    new_users?: number;
    new_users_24h?: number;
    devices_total?: number;
    servers_online: number;
  };
  user_distribution: {
    trial_active: number;
    paid_active: number;
    inactive: number;
    trial_used: number;
    plans: Array<{ label: string; count: number }>;
  };
  charts: {
    traffic: Array<{ label: string; traffic: number; rx: number; tx: number }>;
    user_activity: Array<{ date: string; users: number; revenue: number }>;
    server_load: Array<{ label: string; cpu: number; ram: number; disk: number; connections: number }>;
  };
  rail: {
    alerts: Array<{ title: string; text: string; href: string; action: string }>;
    recent_payments: PaymentRecord[];
    recent_activity: AuditItem[];
  };
  system_alerts: {
    backup: {
      last_backup_at: string;
      backup_stale: boolean;
      status: string;
      priority: string;
      age_hours?: number | null;
      stale_definition_hours: number;
      sources: Array<{
        key: string;
        label: string;
        last_backup_at: string;
        backup_stale: boolean;
        status: string;
        age_hours?: number | null;
        recent_files: number;
        runner?: string;
        offsite_status?: string;
        offsite_synced_at?: string;
      }>;
    };
    restore: {
      last_restore_validation_at: string;
      restore_validation_stale: boolean;
      status: string;
      priority: string;
      age_days?: number | null;
      stale_definition_days: number;
      signal_source: string;
    };
    support: {
      open_tickets: number;
      new_tickets: number;
      priority: string;
      is_escalated: boolean;
      oldest_open_tickets: Array<{
        user_id: number;
        username: string;
        status: string;
        created_at: string;
        updated_at: string;
        preview: string;
        priority: string;
        age_hours?: number | null;
        is_escalated: boolean;
        href: string;
      }>;
      status: string;
    };
    payments: {
      pending_confirmations: number;
      open_manual_requests: number;
      stale_pending_confirmations: number;
      stale_definition_hours: number;
      priority: string;
      is_escalated: boolean;
      oldest_pending_manual_payments: Array<{
        record_id: number;
        user_id?: number | null;
        username: string;
        telegram_id?: number | null;
        created_at: string;
        age_hours: number;
        is_stale: boolean;
        priority: string;
        is_escalated: boolean;
        href: string;
        user_href?: string | null;
      }>;
      status: string;
    };
    nodes?: {
      issues: number;
      degraded: number;
      down: number;
      maintenance: number;
      items: Array<{
        server_id: number;
        name: string;
        status: string;
        status_label: string;
        status_state: string;
        overall_state: string;
        cpu_percent: number;
        memory_used_percent: number;
        disk_used_percent: number;
        href: string;
      }>;
      priority: string;
      status: string;
    };
  };
  attention: {
    repair_needed_users: Array<{
      user_id: number;
      username: string;
      telegram_id: number;
      reason?: string | null;
      reason_label?: string | null;
      marked_at: string;
      marked_age_hours?: number | null;
      access_status: string;
      devices_count: number;
      failed_repair_attempts: number;
      has_repeated_failures: boolean;
      is_payment_related: boolean;
      priority: string;
      is_escalated: boolean;
      can_repair: boolean;
      repair_block_reason?: string | null;
      href: string;
    }>;
    payment_related_users: Array<{
      user_id: number;
      username: string;
      telegram_id: number;
      reason?: string | null;
      marked_at: string;
      failed_repair_attempts: number;
      has_repeated_failures: boolean;
      is_payment_related: boolean;
      href: string;
    }>;
    summary: {
      repair_needed: number;
      repeated_failed_repairs: number;
      payment_related_repairs: number;
      high_priority_repairs: number;
      escalated_repairs: number;
      sync_errors?: number;
      node_issues?: number;
    };
  };
  health: Record<string, unknown>;
};

export type UserRow = {
  id: number;
  username: string;
  telegram_id: number;
  plan: string;
  plan_code?: string | null;
  plan_bucket?: string;
  preferred_protocol: string;
  devices: number;
  payments: number;
  status: string;
  status_state: string;
  status_label: string;
  is_blocked: boolean;
  access_expires_at: string;
  last_device_at: string;
  top_country: string;
  countries?: string[];
  countries_label?: string;
  created_at: string;
  balance_rub?: number;
  base_device_limit?: number;
  extra_device_slots_active?: number;
  extra_device_slots_max?: number;
  max_devices?: number;
  device_limit_reached?: boolean;
  channel_subscription_status?: string;
  channel_subscription_label?: string;
  channel_subscription_checked_at?: string | null;
};

export type UsersPayload = {
  items: UserRow[];
  query: string;
  filters?: {
    status?: string;
    plan?: string;
    issue?: string;
  };
  summary: {
    total: number;
    active: number;
    trial?: number;
    blocked: number;
    with_devices: number;
    waiting_payment?: number;
    needs_repair?: number;
  };
  pagination?: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_prev: boolean;
    has_next: boolean;
    from_item: number;
    to_item: number;
  };
};

export type UserDetailPayload = {
  user: {
    id: number;
    username: string;
    telegram_id: number;
    plan_label: string;
    status: string;
    status_state?: string;
    status_label?: string;
    preferred_protocol: string;
    is_blocked: boolean;
    trial_used: boolean;
    access_expires_at: string;
    created_at: string;
    subscription_started_at?: string | null;
    balance_rub?: number;
    balance_reserved_rub?: number;
    balance_available_rub?: number;
    base_device_limit?: number;
    extra_device_slots_active?: number;
    extra_device_slots_max?: number;
    next_device_slot_expires_at?: string | null;
    max_devices?: number;
    devices_count?: number;
    payments_count?: number;
    countries?: string[];
    countries_label?: string;
    last_known_ip?: string;
    last_known_ip_source_label?: string;
    plan_code?: string | null;
    plan_bucket?: string;
    channel_subscription_status?: string;
    channel_subscription_label?: string;
    channel_subscription_checked_at?: string | null;
    subscription_link_url?: string | null;
    subscription_link_token?: string | null;
    subscription_link_last_viewed_at?: string | null;
    subscription_link_last_feed_accessed_at?: string | null;
  };
  vpn_repair_state: {
    repair_needed: boolean;
    reason?: string | null;
    reason_label?: string | null;
    source?: string | null;
    source_label?: string | null;
    marked_at?: string | null;
  };
  repair_action: {
    can_repair: boolean;
    blocked_reason?: string | null;
  };
  sync_action?: {
    can_sync: boolean;
    blocked_reason?: string | null;
  };
  deep_repair_action?: {
    can_deep_repair: boolean;
    blocked_reason?: string | null;
  };
  vpn_repair_events?: Array<{
    result: string;
    outcome?: string | null;
    outcome_label?: string | null;
    source?: string | null;
    source_label?: string | null;
    reason?: string | null;
    reason_label?: string | null;
    created_at: string;
    }>;
  devices: Array<{
    id: number;
    protocol: string;
    created_at: string;
    mode_label?: string;
    status_key?: string | null;
    status_label?: string | null;
    status_reason?: string | null;
    status_checked_at?: string | null;
    metadata: {
      device_name: string;
      device_type?: string;
      country_name: string;
      ip_address?: string;
      ip_source_label?: string;
      device_source_label?: string;
      can_manage?: boolean;
      subscription_route?: boolean;
      slot_index?: number;
      [key: string]: unknown;
    };
    technical: {
      os_label: string;
      device_model: string;
      os_version: string;
      mac_address: string;
      ip_address: string;
      fallback_ip_address: string;
      ip_history: string;
      ip_source_label: string;
      provider_label: string;
      transport_label: string;
      connection_profile: string;
      node_label: string;
      last_seen_at: string;
      anti_sharing_limit_label: string;
      anti_sharing_scope_label: string;
      anti_sharing_soft_limit_label: string;
      anti_sharing_policy_summary?: string;
    };
  }>;
  payments: PaymentRecord[];
  balance_history?: Array<{
    id: number;
    created_at: string;
    direction: string;
    direction_label: string;
    reason?: string | null;
    reason_label: string;
    amount: number;
    balance_before: number;
    balance_after: number;
    reserved_before?: number;
    reserved_after?: number;
    available_before?: number;
    available_after?: number;
    reference_type?: string | null;
    reference_id?: string | null;
    note?: string | null;
  }>;
  payment_counts: {
    total: number;
    confirmed: number;
    reviewable: number;
  };
  support_ticket?: Record<string, unknown> | null;
  support_history: Array<{
    id?: number;
    role?: string;
    sender_id?: number;
    sender_name?: string;
    content_type?: string;
    text?: string;
    timestamp?: string;
    attachment?: {
      kind?: string | null;
      name?: string | null;
      mime_type?: string | null;
      size?: number | null;
      url?: string | null;
    } | null;
  }>;
  tariffs: Array<Record<string, unknown>>;
  action_result?: UserVpnRepairActionResult | null;
};

export type UserVpnRepairActionResult = {
  sync_failed: boolean;
  repair_needed: boolean;
  reason?: string | null;
  processed_devices?: number;
  successful_devices?: number;
  failed_devices?: number;
  results?: Array<{
    device_id?: number;
    email?: string | null;
    protocol?: string | null;
    status: string;
    reason?: string | null;
  }>;
};

export type ServerNode = {
  id: number;
  name: string;
  country_code: string;
  country_name: string;
  status: string;
  status_label?: string;
  status_state?: string;
  public_ip: string;
  provider: string;
  host: string;
  cpu_percent: number;
  memory_used_percent: number;
  disk_used_percent: number;
  xui_clients: number;
  panel_clients: number;
  active_devices: number;
  total_devices: number;
  active_users: number;
  network_rx_mbps: number;
  network_tx_mbps: number;
  total_network_mbps: number;
  total_transfer_gb: number;
  ping_ms?: number | null;
  ping_label: string;
  uptime: string;
  overall_state: string;
  status_message: string;
  service_pills: Array<{ label: string; value: string }>;
  load: string;
  available_actions?: string[];
  migration_targets?: Array<{
    id: number;
    name: string;
    country_name: string;
    country_code: string;
    status: string;
  }>;
};

export type ServersPayload = {
  summary: Record<string, number>;
  nodes: ServerNode[];
  selected_node?: ServerNode | null;
  vpn_summary: Record<string, number>;
  managed_servers: Array<Record<string, unknown>>;
};

export type TrafficPayload = {
  overview: {
    current_bandwidth: number;
    current_bandwidth_label: string;
    total_transfer_gb: number;
    regions_online: number;
    servers_reporting: number;
    active_connections: number;
    period_label?: string;
    peak_hours_label?: string;
    baseline_reset_at?: string | null;
  };
  bandwidth_by_server: Array<{ server: string; traffic: number; rx: number; tx: number; connections: number; country: string; transfer_gb: number }>;
  load_by_server?: Array<{ server: string; cpu: number; ram: number; disk: number }>;
  connections_by_region: Array<{ region: string; connections: number }>;
  peak_hours: Array<{ hour: string; activity: number }>;
  top_countries: Array<{ country: string; connections: number }>;
  traffic_mix: Array<{ label: string; value: number }>;
  protocol_mix?: Array<{ label: string; value: number }>;
};

export type PaymentRecord = {
  id: number;
  user_id?: number | null;
  username: string;
  telegram_id?: number | null;
  tariff_code: string;
  tariff_label?: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  payment_status_label: string;
  amount: number;
  list_price_amount?: number;
  balance_reserved_amount?: number;
  balance_applied_amount?: number;
  currency: string;
  duration_days: number;
  reference?: string | null;
  note?: string | null;
  reviewed_by_actor_name?: string | null;
  reviewed_at: string;
  rejection_reason?: string | null;
  expires_at: string;
  confirmed_at: string;
  created_at: string;
  is_reviewable: boolean;
  is_waiting_user: boolean;
  is_problem?: boolean;
  can_send_reminder?: boolean;
  available_status_actions?: string[];
  provider_name?: string | null;
  provider_transaction_id?: string | null;
  provider_status?: string | null;
  checkout_url?: string | null;
  last_provider_sync_at?: string | null;
  can_sync_provider?: boolean;
  provider_sync_problem?: string | null;
  linked_user_context?: {
    user_id: number;
    username: string;
    telegram_id?: number | null;
    access_status: string;
    status_state?: string;
    status_label?: string;
    access_expires_at: string;
    devices_count: number;
    max_devices?: number;
    vpn_repair_needed: boolean;
    vpn_repair_reason?: string | null;
    vpn_repair_reason_label?: string | null;
    vpn_repair_source?: string | null;
    vpn_repair_source_label?: string | null;
    repair_action?: {
      can_repair: boolean;
      blocked_reason?: string | null;
    };
    deep_repair_action?: {
      can_deep_repair: boolean;
      blocked_reason?: string | null;
    };
    user_issue_summary?: {
      has_issue: boolean;
      access_status: string;
      devices_count: number;
      vpn_repair_needed: boolean;
      vpn_repair_reason?: string | null;
      vpn_repair_reason_label?: string | null;
      vpn_repair_source?: string | null;
      vpn_repair_source_label?: string | null;
      last_repair_result?: string | null;
      last_repair_outcome?: string | null;
      last_repair_outcome_label?: string | null;
      last_repair_source?: string | null;
      last_repair_source_label?: string | null;
      last_repair_reason?: string | null;
      last_repair_reason_label?: string | null;
      last_repair_at?: string | null;
      can_repair?: boolean;
      repair_block_reason?: string | null;
    } | null;
    support_ticket_open: boolean;
    support_status?: string | null;
    user_href: string;
    support_href?: string | null;
  } | null;
};

export type FinanceEntry = {
  id: number;
  entry_type: string;
  entry_type_label: string;
  status: string;
  status_label: string;
  category: string;
  amount: number;
  currency: string;
  signed_amount: number;
  note?: string | null;
  related_server?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  period_key: string;
  occurred_at: string;
  approved_at: string;
  created_by_name: string;
  counterparty_name: string;
  approved_by_name: string;
  is_recurring: boolean;
};

export type PaymentsPayload = {
  summary: {
    mrr: number;
    new_subscriptions: number;
    refunds: number;
    failed_payments: number;
    manual_queue: number;
    awaiting_payment?: number;
    confirmed?: number;
    expired?: number;
    disputed?: number;
    error?: number;
    problem_records?: number;
  };
  records: PaymentRecord[];
  selected_record?: PaymentRecord | null;
  payment_mix: Array<{ method: string; count: number }>;
  finance: {
    summary: Record<string, unknown>;
    dashboard: {
      summary: Record<string, unknown>;
      entries: FinanceEntry[];
      selected_entry?: FinanceEntry | null;
      periods: string[];
      admins: Array<{ id: number; display_name: string; role_name: string }>;
      filters: Record<string, unknown>;
      recurring_rows: FinanceEntry[];
    };
  };
  tariffs: Array<Record<string, unknown>>;
};

export type CampaignAnalyticsStats = {
  transitions: number;
  bot_starts: number;
  trial_started: number;
  key_issued: number;
  paid: number;
  renewed: number;
  conversion_rate: number;
};

export type CampaignAnalyticsRow = {
  id: number;
  token: string;
  name: string;
  tracking_url: string;
  created_at: string;
  status: string;
  status_label: string;
  cta_label: string;
  stats: CampaignAnalyticsStats;
};

export type CampaignAnalyticsFunnelStage = {
  stage: string;
  count: number;
  rate: number;
};

export type CampaignAnalyticsPayload = {
  summary: {
    total_campaigns: number;
    total_transitions: number;
    total_bot_starts: number;
    total_trial_started: number;
    total_key_issued: number;
    total_paid: number;
    total_renewed: number;
    overall_conversion_rate: number;
  };
  query: string;
  period?: {
    key: string;
    label: string;
    start: string;
    end: string;
    presets?: string[];
  };
  campaigns: CampaignAnalyticsRow[];
};

export type CampaignAnalyticsDetailPayload = CampaignAnalyticsRow & {
  funnel: CampaignAnalyticsFunnelStage[];
  period?: {
    key: string;
    label: string;
    start: string;
    end: string;
  };
};

export type PromoCodesPayload = {
  summary: {
    total: number;
    active: number;
    discounts: number;
    days: number;
    gift: number;
    pending_discount_redemptions: number;
  };
  filters: {
    search: string;
    kind: string;
    status: string;
  };
  codes: Array<{
    id: number;
    code: string;
    kind: string;
    kind_label: string;
    title: string;
    description: string;
    discount_percent?: number | null;
    grant_days: number;
    max_redemptions: number;
    redeemed_count: number;
    remaining_redemptions: number;
    status: string;
    status_label: string;
    created_by_name: string;
    buyer_label: string;
    buyer_user_id?: number | null;
    payment_record_id?: number | null;
    expires_at?: string | null;
    created_at: string;
  }>;
};

export type SupportPayload = {
  tickets: Array<Record<string, unknown>>;
  counts: Record<string, number>;
  filter_mode: string;
  query: string;
  selected_ticket?: {
    ticket: Record<string, unknown>;
    history: Array<Record<string, unknown>>;
    user?: {
      id?: number;
      username?: string;
      telegram_id?: number | null;
    } | null;
    payments: PaymentRecord[];
    payment_counts: Record<string, number>;
    linked_user_context?: {
      user_id: number;
      username: string;
      telegram_id?: number | null;
      plan_label: string;
      trial_used: boolean;
      can_grant_trial: boolean;
      can_extend_access: boolean;
      access_status: string;
      status_state?: string;
      status_label?: string;
      access_expires_at: string;
      devices_count: number;
      max_devices?: number;
      vpn_repair_needed: boolean;
      vpn_repair_reason?: string | null;
      vpn_repair_reason_label?: string | null;
      repair_action?: {
        can_repair: boolean;
        blocked_reason?: string | null;
      };
      sync_action?: {
        can_sync: boolean;
        blocked_reason?: string | null;
      };
      deep_repair_action?: {
        can_deep_repair: boolean;
        blocked_reason?: string | null;
      };
      support_ticket_open: boolean;
      support_status?: string | null;
      user_href: string;
      latest_payment_href?: string | null;
    } | null;
  } | null;
  admin_choices: Array<{
    telegram_id: number;
    display_name: string;
    role_name: string;
    is_current: boolean;
  }>;
};

export type SettingsPayload = {
  service_statuses: Record<string, { label: string; status: string }>;
  logs: Record<string, string>;
  env_rows: Array<[string, string]>;
  api_keys: Array<[string, string]>;
  audits: AuditItem[];
  tariffs: Record<string, number>;
  tariff_options: Array<Record<string, unknown>>;
  docs: Record<string, unknown>;
  docs_settings: Record<string, unknown>;
  managed_servers: Array<Record<string, unknown>>;
  payment_methods: Record<string, boolean>;
  available_roles?: Array<{
    value: string;
    label: string;
  }>;
  admins?: Array<{
    id: number;
    display_name: string;
    username: string;
    role: string;
    role_name: string;
    telegram_id?: number | null;
    is_active: boolean;
  }>;
  role_matrix?: Array<{
    permission: string;
    label?: string;
    owner: boolean;
    owner_editable?: boolean;
    tech_admin: boolean;
    tech_admin_editable?: boolean;
    manager: boolean;
    manager_editable?: boolean;
  }>;
  notification_profiles?: Array<{
    telegram_id: number;
    role: string;
    display_name: string;
    username?: string | null;
    enabled_count: number;
    total_count: number;
    preferences: Record<string, boolean>;
    categories?: Array<{
      key: string;
      label: string;
      enabled: boolean;
      mandatory: boolean;
    }>;
  }>;
  integrations?: Array<{
    key: string;
    label: string;
    status: string;
    description: string;
  }>;
  updated_admin?: {
    id: number;
    display_name: string;
    username: string;
    role: string;
    role_name: string;
    telegram_id?: number | null;
    is_active: boolean;
  };
  service_action_result?: {
    service_name?: string;
    action?: string;
    status?: string;
    label?: string;
  };
  env_update_result?: {
    key?: string;
    restart_required?: boolean;
    affected_services?: string[];
    runtime_apply?: {
      applied_ok?: boolean;
      applied_services?: string[];
      verified_services?: string[];
      failed_services?: { service_name: string; error: string }[];
      rolled_back?: boolean;
      rollback_ok?: boolean | null;
      rollback_verified_services?: string[];
      rollback_failed_services?: { service_name: string; error: string }[];
      runtime_state?: string;
    } | null;
  };
  updated_notification_preference?: {
    telegram_id: number;
    category: string;
    enabled: boolean;
    preferences: Record<string, boolean>;
  };
  updated_role_permission?: {
    role: string;
    permission: string;
    enabled: boolean;
  };
};

export type UserDeviceStatusPayload = {
  device_id: number;
  mode_label?: string;
  status_key?: string | null;
  status_label?: string | null;
  status_reason?: string | null;
  status_checked_at?: string | null;
};

export type KnowledgePayload = {
  docs: Record<string, unknown>;
  docs_settings: Record<string, unknown>;
};
