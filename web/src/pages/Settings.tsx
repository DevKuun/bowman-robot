import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit2, Check, X, Key, Shield } from 'lucide-react';
import { accountsApi } from '../api/client';
import type { Account } from '../types';

const exchangeColors: Record<string, string> = {
  UPBIT: 'from-blue-500 to-blue-600',
  BITHUMB: 'from-orange-500 to-amber-500',
  KORBIT: 'from-purple-500 to-violet-500',
  BINANCE: 'from-yellow-400 to-yellow-500',
};

const riskLabels = ['매우 안전', '안전', '보통', '공격적', '매우 공격적'];

export function Settings() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [newAccount, setNewAccount] = useState({
    exchange: 'upbit',
    access_key: '',
    secret_key: '',
    risk_level: 2,
  });

  const [editRiskLevel, setEditRiskLevel] = useState(2);

  const accountsQuery = useQuery({
    queryKey: ['accounts'],
    queryFn: accountsApi.getAll,
  });

  const createMutation = useMutation({
    mutationFn: accountsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setShowAddForm(false);
      setNewAccount({ exchange: 'upbit', access_key: '', secret_key: '', risk_level: 2 });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, params }: { id: string; params: any }) => 
      accountsApi.update(id, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: accountsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  const handleCreate = () => {
    createMutation.mutate(newAccount);
  };

  const handleUpdate = (id: string) => {
    updateMutation.mutate({ id, params: { risk_level: editRiskLevel } });
  };

  const handleDelete = (id: string) => {
    if (confirm('정말로 이 계정을 비활성화하시겠습니까?')) {
      deleteMutation.mutate(id);
    }
  };

  const startEdit = (account: Account) => {
    setEditingId(account.id);
    setEditRiskLevel(account.risk_level);
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">설정</h1>
          <p className="text-gray-500 text-sm mt-1">거래소 계정 관리</p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="btn btn-primary"
        >
          <Plus className="w-4 h-4" />
          계정 추가
        </button>
      </div>

      {/* Add Account Form */}
      {showAddForm && (
        <div className="card border-2 border-blue-100">
          <h3 className="text-lg font-semibold text-gray-800 mb-5">거래소 계정 추가</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-2">거래소</label>
              <select
                value={newAccount.exchange}
                onChange={(e) => setNewAccount({ ...newAccount, exchange: e.target.value })}
                className="input"
              >
                <option value="upbit">업비트 (Upbit)</option>
                <option value="bithumb">빗썸 (Bithumb)</option>
                <option value="korbit">코빗 (Korbit)</option>
                <option value="binance">바이낸스 (Binance)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-2">리스크 레벨</label>
              <select
                value={newAccount.risk_level}
                onChange={(e) => setNewAccount({ ...newAccount, risk_level: Number(e.target.value) })}
                className="input"
              >
                {[0, 1, 2, 3, 4].map(level => (
                  <option key={level} value={level}>
                    {level} - {riskLabels[level]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-2">Access Key</label>
              <input
                type="password"
                value={newAccount.access_key}
                onChange={(e) => setNewAccount({ ...newAccount, access_key: e.target.value })}
                className="input"
                placeholder="API Access Key 입력"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-2">Secret Key</label>
              <input
                type="password"
                value={newAccount.secret_key}
                onChange={(e) => setNewAccount({ ...newAccount, secret_key: e.target.value })}
                className="input"
                placeholder="API Secret Key 입력"
              />
            </div>
          </div>
          <div className="flex gap-3 mt-5">
            <button
              onClick={handleCreate}
              disabled={createMutation.isPending || !newAccount.access_key || !newAccount.secret_key}
              className="btn btn-success"
            >
              {createMutation.isPending ? '생성 중...' : '계정 생성'}
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="btn bg-gray-100 text-gray-700 hover:bg-gray-200"
            >
              취소
            </button>
          </div>
          {createMutation.isError && (
            <p className="mt-3 text-red-600 text-sm">
              {(createMutation.error as any)?.response?.data?.detail || '계정 생성에 실패했습니다'}
            </p>
          )}
        </div>
      )}

      {/* Accounts List */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-800 mb-5">등록된 계정</h3>
        
        {accountsQuery.isLoading ? (
          <div className="animate-pulse space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-20 bg-gray-50 rounded-xl"></div>
            ))}
          </div>
        ) : accountsQuery.data?.accounts?.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-2xl flex items-center justify-center">
              <Key className="w-8 h-8 text-gray-400" />
            </div>
            <p className="text-gray-600 font-medium">등록된 계정이 없습니다</p>
            <p className="text-sm text-gray-400 mt-1">실거래를 위해 거래소 API 키를 등록하세요</p>
          </div>
        ) : (
          <div className="space-y-3">
            {accountsQuery.data?.accounts?.map((account) => (
              <div
                key={account.id}
                className={`p-5 border rounded-xl transition-all ${
                  account.is_active 
                    ? 'border-gray-200 hover:border-gray-300 hover:shadow-sm' 
                    : 'border-gray-100 bg-gray-50/50 opacity-60'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${exchangeColors[account.exchange] || 'from-gray-400 to-gray-500'} flex items-center justify-center text-white font-bold shadow-lg`}>
                      {account.exchange[0]}
                    </div>
                    <div>
                      <p className="font-semibold text-gray-800">{account.exchange}</p>
                      <p className="text-sm text-gray-400">
                        ID: {account.id.slice(0, 8)}...
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    {editingId === account.id ? (
                      <div className="flex items-center gap-3">
                        <select
                          value={editRiskLevel}
                          onChange={(e) => setEditRiskLevel(Number(e.target.value))}
                          className="input w-auto py-2"
                        >
                          {[0, 1, 2, 3, 4].map(level => (
                            <option key={level} value={level}>리스크 {level}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => handleUpdate(account.id)}
                          className="p-2 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                        >
                          <Check className="w-5 h-5" />
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="p-2 text-gray-400 hover:bg-gray-100 rounded-lg transition-colors"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center gap-2">
                          <Shield className="w-4 h-4 text-gray-400" />
                          <div className="text-right">
                            <p className="text-xs text-gray-400">리스크</p>
                            <p className="font-semibold text-gray-800">{riskLabels[account.risk_level]}</p>
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <button
                            onClick={() => startEdit(account)}
                            className="p-2.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(account.id)}
                            className="p-2.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {!account.is_active && (
                  <p className="mt-3 text-sm text-gray-400">비활성화됨</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
