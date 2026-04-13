'use client';

import { useEffect, useState } from 'react';
import { useSession } from '@/hooks/use-dashboard';

interface Campaign {
  id: number;
  name: string;
  token: string;
  cta_label: string;
  is_active: boolean;
  tracking_url: string;
  created_at: string;
  stats: {
    transitions: number;
    bot_starts: number;
    trial_started: number;
    key_issued: number;
    paid: number;
    renewed: number;
    conversion_rate: number;
  };
}

export default function CampaignsPage() {
  const session = useSession();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState('');

  useEffect(() => {
    fetch('/api/proxy/dashboard/api/v2/campaigns', { credentials: 'include' })
      .then(res => res.json())
      .then(res => setCampaigns(res.data?.campaigns || []))
      .catch(() => setCampaigns([]))
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const formData = new FormData();
      formData.append('name', newName);
      await fetch('/api/proxy/dashboard/api/v2/campaigns/create', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      window.location.reload();
    } catch (err) {
      alert('Ошибка создания кампании');
    }
  };

  const handleToggle = async (id: number) => {
    await fetch(`/api/proxy/dashboard/api/v2/campaigns/${id}/toggle`, {
      method: 'POST',
      credentials: 'include',
    });
    window.location.reload();
  };

  const handleDelete = async (id: number) => {
    if (confirm('Удалить кампанию?')) {
      await fetch(`/api/proxy/dashboard/api/v2/campaigns/${id}/delete`, {
        method: 'POST',
        credentials: 'include',
      });
      window.location.reload();
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-950 dark:text-slate-50">Маркетинговые кампании</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Трекинг-ссылки и конверсии</p>
        </div>
        <button onClick={() => setShowModal(true)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          + Новая кампания
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500">Загрузка...</div>
      ) : campaigns.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-6 py-12 text-center dark:border-slate-800 dark:bg-slate-900/50">
          <p className="text-slate-500 dark:text-slate-400">Кампаний пока нет</p>
          <button onClick={() => setShowModal(true)} className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
            Создать первую кампанию
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {campaigns.map(c => (
            <div key={c.id} className="rounded-xl border border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900/70">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-slate-950 dark:text-slate-50">{c.name}</h2>
                  <span className={`inline-block mt-1 rounded-full px-2 py-0.5 text-xs font-medium ${c.is_active ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
                    {c.is_active ? 'Активна' : 'Неактивна'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleToggle(c.id)} className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                    {c.is_active ? 'Деактивировать' : 'Активировать'}
                  </button>
                  <button onClick={() => handleDelete(c.id)} className="rounded-md bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50">
                    Удалить
                  </button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-4 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">
                <div className="text-center"><div className="text-lg font-bold text-blue-600">{c.stats.transitions}</div><div className="text-xs text-slate-500">Переходы</div></div>
                <div className="text-center"><div className="text-lg font-bold text-blue-600">{c.stats.bot_starts}</div><div className="text-xs text-slate-500">/start</div></div>
                <div className="text-center"><div className="text-lg font-bold text-blue-600">{c.stats.trial_started}</div><div className="text-xs text-slate-500">Триалы</div></div>
                <div className="text-center"><div className="text-lg font-bold text-emerald-600">{c.stats.paid}</div><div className="text-xs text-slate-500">Оплаты</div></div>
                <div className="text-center"><div className="text-lg font-bold text-emerald-600">{c.stats.conversion_rate}%</div><div className="text-xs text-slate-500">Конверсия</div></div>
              </div>
              <div className="mt-2 flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-800/50">
                <code className="flex-1 truncate text-xs text-slate-600 dark:text-slate-400">{c.tracking_url}</code>
                <button onClick={() => navigator.clipboard.writeText(c.tracking_url)} className="text-slate-400 hover:text-slate-600">📋</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-xl bg-white p-6 dark:bg-slate-900" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-slate-950 dark:text-slate-50">Новая кампания</h2>
            <form onSubmit={handleCreate} className="mt-4">
              <label className="block">
                <span className="text-sm text-slate-600 dark:text-slate-400">Название</span>
                <input type="text" value={newName} onChange={e => setNewName(e.target.value)} required className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" placeholder="Реклама в Telegram" />
              </label>
              <div className="mt-4 flex justify-end gap-2">
                <button type="button" onClick={() => setShowModal(false)} className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">Отмена</button>
                <button type="submit" className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">Создать</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
