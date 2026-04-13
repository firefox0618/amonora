import { UserVpnRepairActionResult } from "@/lib/types";

export type RepairFeedback = {
  title: string;
  description: string;
  tone: "success" | "warning" | "error";
  bannerTone: "success" | "warning" | "error";
};

export function repairReasonLabel(reason?: string | null): string {
  if (reason === "manual_repair_no_devices") return "no devices";
  if (reason === "manual_repair_no_access") return "no active access";
  if (reason === "manual_repair_sync_failed") return "sync error";
  if (reason === "post_payment_sync_failed") return "post-payment sync error";
  if (reason === "post_payment_access_incomplete") return "post-payment access incomplete";
  return reason || "unknown issue";
}

export function describeRepairResult(result: UserVpnRepairActionResult): RepairFeedback {
  if (!result.sync_failed) {
    return {
      title: "Repair succeeded",
      description: "Access state resynced and repair-needed marker was cleared.",
      tone: "success",
      bannerTone: "success",
    };
  }
  if (result.reason === "manual_repair_no_devices") {
    return {
      title: "Repair skipped",
      description: "No devices are attached to this user, so repair was not started.",
      tone: "warning",
      bannerTone: "warning",
    };
  }
  if (result.reason === "manual_repair_no_access") {
    return {
      title: "Repair skipped",
      description: "User has no active access, so repair was not started.",
      tone: "warning",
      bannerTone: "warning",
    };
  }
  return {
    title: "Repair failed",
    description: `Access sync still needs manual attention: ${repairReasonLabel(result.reason)}.`,
    tone: "warning",
    bannerTone: "error",
  };
}

export function summarizeBatchRepair(
  results: Array<{ userId: number; status: "success" | "failed"; reason?: string | null }>,
): RepairFeedback {
  const succeeded = results.filter((item) => item.status === "success").length;
  const failed = results.length - succeeded;
  if (failed === 0) {
    return {
      title: "Batch repair completed",
      description: `Processed ${succeeded} users successfully.`,
      tone: "success",
      bannerTone: "success",
    };
  }
  const firstFailure = results.find((item) => item.status === "failed");
  return {
    title: "Batch repair completed with issues",
    description: `success ${succeeded} · failed ${failed}${firstFailure?.reason ? ` · first issue: ${repairReasonLabel(firstFailure.reason)}` : ""}`,
    tone: "warning",
    bannerTone: "warning",
  };
}
