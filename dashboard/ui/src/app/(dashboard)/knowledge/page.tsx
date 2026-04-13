"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Button, Card, NoticeBanner, SectionHeading } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useKnowledge } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";

type DocSection = { title: string; items: Array<{ slug: string; title: string; summary?: string }> };

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return true;
  return window.confirm(message);
}

export default function KnowledgePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const selectedDoc = searchParams.get("doc") || undefined;
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const knowledgeQuery = useKnowledge(selectedDoc);

  const reportMutation = useMutation({
    mutationFn: () => apiPost("/settings/docs/report"),
    onSuccess: async () => {
      setError("");
      setNotice("Операционный отчёт обновлён и опубликован в базе знаний.");
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
    },
  });

  const docSections = useMemo(() => {
    const sections = (knowledgeQuery.data?.docs.sections || []) as DocSection[];
    if (!search.trim()) {
      return sections;
    }
    const needle = search.trim().toLowerCase();
    return sections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) =>
          `${item.title} ${item.summary || ""} ${item.slug}`.toLowerCase().includes(needle),
        ),
      }))
      .filter((section) => section.items.length > 0);
  }, [knowledgeQuery.data?.docs.sections, search]);

  if (knowledgeQuery.isLoading) return <PageLoader />;
  if (knowledgeQuery.error || !knowledgeQuery.data) {
    return <PageError message={knowledgeQuery.error?.message || "Не удалось загрузить базу знаний"} />;
  }

  const docs = knowledgeQuery.data.docs as {
    title: string;
    description: string;
    current?: {
      slug?: string;
      title?: string;
      summary?: string;
      github_url?: string;
      raw_url?: string;
      html?: string;
    } | null;
    source_label?: string;
    folder_url?: string;
    repo_url?: string;
    branch?: string;
    report_item?: { slug?: string } | null;
  };
  const currentDoc = docs.current || null;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Knowledge hub"
        title="База знаний и операционные статьи"
        description="Документация, runbook, generated-отчёты и внутренняя операционная база знаний Amonora в одном месте."
        actions={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                if (!confirmAction("Сгенерировать новый операционный отчёт и перезаписать текущую версию?")) {
                  return;
                }
                reportMutation.mutate();
              }}
              disabled={reportMutation.isPending}
            >
              {reportMutation.isPending ? "Генерирую..." : "Сгенерировать отчёт"}
            </Button>
            {docs.folder_url ? (
              <Link href={docs.folder_url} target="_blank" className="inline-flex">
                <Button variant="ghost">Открыть папку</Button>
              </Link>
            ) : null}
            {currentDoc?.github_url ? (
              <Link href={currentDoc.github_url} target="_blank" className="inline-flex">
                <Button>Открыть в GitHub</Button>
              </Link>
            ) : null}
          </>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Documentation</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{docs.title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{docs.description}</p>
          </div>

          <input
            id="knowledge-search"
            name="knowledgeSearch"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Найти статью, отчёт, runbook..."
            className="h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
          />

          <div className="max-h-[68vh] space-y-4 overflow-auto pr-1">
            {docSections.map((section) => (
              <div key={section.title} className="space-y-2">
                <div className="px-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">{section.title}</div>
                <div className="space-y-2">
                  {section.items.map((item) => {
                    const active = currentDoc?.slug === item.slug;
                    return (
                      <button
                        key={item.slug}
                        type="button"
                        onClick={() => router.replace(`/knowledge?doc=${encodeURIComponent(item.slug)}`, { scroll: false })}
                        className={`w-full rounded-[22px] border px-4 py-3 text-left transition ${
                          active
                            ? "border-blue-200 bg-blue-50 text-slate-950 shadow-[0_16px_40px_-28px_rgba(37,99,235,0.45)] dark:border-blue-500/25 dark:bg-blue-500/10 dark:text-slate-50"
                            : "border-slate-200 bg-slate-50/90 text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:bg-slate-800/90"
                        }`}
                      >
                        <div className="font-semibold">{item.title}</div>
                        {item.summary ? <div className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">{item.summary}</div> : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="min-w-0">
          {currentDoc ? (
            <div className="space-y-5">
              <div className="space-y-3 border-b border-slate-200 pb-5 dark:border-slate-800">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                    {docs.source_label || "Документ"}
                  </span>
                  {docs.branch ? (
                    <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-blue-600 dark:bg-blue-500/10 dark:text-blue-300">
                      {docs.branch}
                    </span>
                  ) : null}
                </div>
                <div>
                  <h3 className="text-3xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                    {currentDoc.title || "Документ"}
                  </h3>
                  {currentDoc.summary ? <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{currentDoc.summary}</p> : null}
                </div>
                <div className="flex flex-wrap gap-3">
                  {currentDoc.github_url ? (
                    <Link href={currentDoc.github_url} target="_blank" className="inline-flex">
                      <Button variant="ghost">GitHub source</Button>
                    </Link>
                  ) : null}
                  {currentDoc.raw_url ? (
                    <Link href={currentDoc.raw_url} target="_blank" className="inline-flex">
                      <Button variant="ghost">Raw markdown</Button>
                    </Link>
                  ) : null}
                </div>
              </div>

              <article
                className="prose-v2 max-w-none"
                dangerouslySetInnerHTML={{ __html: currentDoc.html || "<p>Документ пуст.</p>" }}
              />
            </div>
          ) : (
            <div className="flex min-h-[420px] items-center justify-center text-center">
              <div>
                <h3 className="text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">Выбери статью</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                  Открой любую статью слева, чтобы увидеть полное содержимое, ссылки на исходник и generated-отчёты.
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
