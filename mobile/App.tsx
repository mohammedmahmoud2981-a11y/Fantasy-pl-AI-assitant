import { StatusBar } from 'expo-status-bar';
import { router, type Href } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar as NativeStatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const C = {
  bg: '#07111F', panel: '#101D2D', panel2: '#16263A', line: '#22364D',
  text: '#F4F7FB', muted: '#9AAEC2', lime: '#D9FB57', mint: '#76E5C4',
  blue: '#73AEFF', coral: '#FF8B79', amber: '#F8C969',
};

type Player = {
  id: number; player: string; position: string; team_name: string; cost_m: number;
  expected_points: number; total_points: number; points_per_game: number;
  minutes: number; form: number; selected_by_percent: number; status: string;
  fantasyiq_points?: number;
  high_potential_probability?: number;
};
type Overview = {
  player_count: number; available_count: number; club_count: number;
  gameweek?: { id: number; name?: string; deadline_time?: string } | null;
  prediction_gameweek?: number | null; model_ready?: boolean;
};
type Squad = {
  cost: number; remaining_budget: number; combined_fantasyiq_projection: number;
  prediction_gameweek?: number | null; fantasyiq_players: number; fpl_fallback_players: number;
  players: Player[];
};
type TransferAdvice = {
  current_player: Player; current_projection: number; position: string;
  free_transfers: number; hit_points: number;
  prediction_gameweek?: number | null;
  recommendations: (Player & { points_gain: number; net_points_gain: number; transfer_cost: number; price_difference: number; value_per_million: number })[];
};
type TransferPlan = { transfers: number; free_transfers_used: number; hit_points: number; gross_points_gain: number; net_points_gain: number; cost_delta: number; remaining_bank: number; projected_squad_points: number; replacements: { out: Player; in: Player; points_gain: number; price_difference: number }[] };
type ImportedTeam = { entry_id: number; team_name: string; manager: string; event: number; bank: number; free_transfers: number; players: Player[] };
type ProfileResponse = { metrics: { clusters: number; silhouette_score: number; source_season: string; anomaly_count: number }; players: (Player & { cluster: number; anomaly_score: number; is_anomaly: boolean })[]; count: number };
type Tab = 'الرئيسية' | 'اللاعبون' | 'فريقي';

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    let message = `خطأ من الخادم (${response.status})`;
    try {
      const payload = await response.json();
      if (payload.detail) message = payload.detail;
    } catch { /* Keep the status message. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function Label({ children, color = C.muted, style }: { children: React.ReactNode; color?: string; style?: object }) {
  return <Text style={[styles.label, { color }, style]}>{children}</Text>;
}

function Metric({ title, value, accent = C.text }: { title: string; value: string; accent?: string }) {
  return (
    <View style={styles.metric}>
      <Label>{title}</Label>
      <Text style={[styles.metricValue, { color: accent }]}>{value}</Text>
    </View>
  );
}

function PlayerRow({ player, rank }: { player: Player; rank?: number }) {
  const hasModelPrediction = typeof player.fantasyiq_points === 'number' && Number.isFinite(player.fantasyiq_points);
  const displayedPoints = hasModelPrediction ? player.fantasyiq_points! : player.expected_points;
  return (
    <View style={styles.playerRow}>
      <View style={styles.playerIdentity}>
        {rank !== undefined && <Text style={styles.rank}>{String(rank).padStart(2, '0')}</Text>}
        <View style={styles.avatar}><Text style={styles.avatarText}>{player.player.split(' ').slice(-1)[0]?.slice(0, 1) || '⚽'}</Text></View>
        <View style={styles.playerCopy}>
          <Text numberOfLines={1} style={styles.playerName}>{player.player}</Text>
          <Text numberOfLines={1} style={styles.playerMeta}>{player.team_name}  ·  {player.position}</Text>
          {(player.high_potential_probability ?? 0) >= 0.65 && <Text style={styles.potentialBadge}>مرشح قوي · {Math.round(player.high_potential_probability! * 100)}%</Text>}
        </View>
      </View>
      <View style={styles.playerNumbers}>
        <Text style={styles.playerXp}>{Number(displayedPoints || 0).toFixed(1)}</Text>
        <Text style={styles.playerPrice}>{hasModelPrediction ? 'FantasyIQ' : 'FPL xP'} · £{Number(player.cost_m || 0).toFixed(1)}m</Text>
      </View>
    </View>
  );
}

export function FantasyApp({ page }: { page: Tab }) {
  const tab = page;
  const [overview, setOverview] = useState<Overview | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [squad, setSquad] = useState<Squad | null>(null);
  const [budget, setBudget] = useState(100);
  const [positionFilter, setPositionFilter] = useState('الكل');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null);
  const [transferBudget, setTransferBudget] = useState(0);
  const [freeTransfers, setFreeTransfers] = useState(1);
  const [hitPoints, setHitPoints] = useState(0);
  const [transferAdvice, setTransferAdvice] = useState<TransferAdvice | null>(null);
  const [loadingTransfers, setLoadingTransfers] = useState(false);
  const [selectedOutgoingIds, setSelectedOutgoingIds] = useState<number[]>([]);
  const [transferPlans, setTransferPlans] = useState<TransferPlan[]>([]);
  const [planBank, setPlanBank] = useState(0);
  const [planningTransfers, setPlanningTransfers] = useState(false);
  const [entryId, setEntryId] = useState('');
  const [importedTeam, setImportedTeam] = useState<ImportedTeam | null>(null);
  const [importingTeam, setImportingTeam] = useState(false);
  const [profiles, setProfiles] = useState<ProfileResponse | null>(null);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    try {
      const [summary, result] = await Promise.all([
        api<Overview>('/api/overview'),
        api<{ players: Player[] }>('/api/players?limit=700'),
      ]);
      setOverview(summary);
      setPlayers(result.players);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'تعذّر الاتصال بالخادم');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const topPlayers = useMemo(
    () => [...players].sort((a, b) => (b.fantasyiq_points ?? b.expected_points) - (a.fantasyiq_points ?? a.expected_points)).slice(0, 5),
    [players],
  );
  const filteredPlayers = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return players.filter((player) => {
      const matchesPosition = positionFilter === 'الكل' || player.position === positionFilter;
      const matchesQuery = !needle || player.player.toLocaleLowerCase().includes(needle) || player.team_name.toLocaleLowerCase().includes(needle);
      return matchesPosition && matchesQuery;
    });
  }, [players, positionFilter, query]);

  const runOptimizer = async () => {
    setOptimizing(true);
    try {
      setSquad(await api<Squad>(`/api/squad?budget=${budget}`));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'تعذّر تحسين التشكيلة');
    } finally {
      setOptimizing(false);
    }
  };

  const findTransfers = async (player: Player) => {
    setSelectedPlayerId(player.id);
    setLoadingTransfers(true);
    setTransferAdvice(null);
    try {
      setTransferAdvice(await api<TransferAdvice>(`/api/recommendations/transfers?player_id=${player.id}&budget=${transferBudget}&limit=5&free_transfers=${freeTransfers}&extra_transfers=${hitPoints}`));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'تعذّر تحميل بدائل اللاعب');
    } finally {
      setLoadingTransfers(false);
    }
  };

  const buildTransferPlan = async () => {
    const activeSquad = importedTeam ?? squad;
    if (!activeSquad || selectedOutgoingIds.length === 0) return;
    setPlanningTransfers(true);
    try {
      const query = new URLSearchParams({ player_ids: selectedOutgoingIds.join(','), squad_ids: activeSquad.players.map((p) => p.id).join(','), bank: String(importedTeam?.bank ?? planBank), free_transfers: String(importedTeam?.free_transfers ?? freeTransfers), limit: '3' });
      const result = await api<{ plans: TransferPlan[] }>(`/api/recommendations/plan?${query.toString()}`);
      setTransferPlans(result.plans);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'تعذّر إعداد خطة الانتقالات');
    } finally {
      setPlanningTransfers(false);
    }
  };

  const importFplTeam = async () => {
    const id = Number(entryId.trim());
    if (!Number.isInteger(id) || id < 1) { setError('أدخل رقم فريق FPL صحيحًا.'); return; }
    setImportingTeam(true);
    try {
      const result = await api<ImportedTeam>(`/api/fpl-team/${id}`);
      setImportedTeam(result); setSelectedOutgoingIds([]); setTransferPlans([]); setPlanBank(result.bank); setFreeTransfers(result.free_transfers); setError('');
    } catch (err) { setError(err instanceof Error ? err.message : 'تعذّر استيراد فريق FPL'); }
    finally { setImportingTeam(false); }
  };

  const loadProfiles = async () => {
    setLoadingProfiles(true);
    try { setProfiles(await api<ProfileResponse>('/api/analytics/player-profiles?limit=30')); }
    catch (err) { setError(err instanceof Error ? err.message : 'تعذّر تحميل تحليل اللاعبين'); }
    finally { setLoadingProfiles(false); }
  };

  const positions = ['الكل', 'Goalkeeper', 'Defender', 'Midfielder', 'Forward'];
  const positionNames: Record<string, string> = {
    الكل: 'الكل', Goalkeeper: 'حارس', Defender: 'دفاع', Midfielder: 'وسط', Forward: 'هجوم',
  };

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <NativeStatusBar barStyle="light-content" />
      <View style={styles.topBar}>
        <View style={styles.brandMark}><Text style={styles.brandBall}>⚽</Text></View>
        <View style={styles.brandText}>
          <Text style={styles.brandName}>FANTASY<Text style={{ color: C.lime }}>IQ</Text></Text>
          <Text style={styles.brandSub}>ذكاء فانتازي الدوري الإنجليزي</Text>
        </View>
        <Pressable onPress={() => void loadData(true)} style={styles.refreshButton} accessibilityLabel="تحديث البيانات">
          <Text style={styles.refreshGlyph}>↻</Text>
        </Pressable>
      </View>

      {error ? (
        <View style={styles.errorCard}>
          <Text style={styles.errorTitle}>تعذّر تحميل البيانات</Text>
          <Text style={styles.errorBody}>{error}</Text>
          <Text style={styles.errorHint}>شغّل خادم FantasyIQ على الكمبيوتر، واجعل EXPO_PUBLIC_API_URL يشير إلى عنوانه على الشبكة.</Text>
          <Pressable onPress={() => void loadData()} style={styles.retryButton}><Text style={styles.retryText}>إعادة المحاولة</Text></Pressable>
        </View>
      ) : null}

      {loading && !players.length ? (
        <View style={styles.loading}><ActivityIndicator size="large" color={C.lime} /><Text style={styles.loadingText}>نجهز بيانات الجولة…</Text></View>
      ) : (
        <ScrollView
          style={styles.content}
          contentContainerStyle={styles.contentInner}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void loadData(true)} tintColor={C.lime} />}
        >
          {tab === 'الرئيسية' && (
            <>
              <View style={styles.welcomeRow}>
                <View><Label color={C.mint}>مركزك التحليلي</Label><Text style={styles.screenTitle}>خليك سابق الجولة</Text></View>
                <View style={styles.livePill}><View style={styles.liveDot} /><Text style={styles.liveText}>مباشر</Text></View>
              </View>

              <View style={styles.heroCard}>
                <View style={styles.heroDecor} />
                <View style={styles.heroTop}>
                  <View><Text style={styles.heroEyebrow}>توقع الجولة القادمة</Text><Text style={styles.heroGw}>GW {overview?.prediction_gameweek ?? overview?.gameweek?.id ?? '—'}</Text></View>
                  <Text style={styles.heroIcon}>✦</Text>
                </View>
                <View style={styles.heroDivider} />
                <View style={styles.heroBottom}>
                  <View><Text style={styles.heroBig}>{players.length ? topPlayers.reduce((sum, player) => sum + (player.fantasyiq_points ?? player.expected_points), 0).toFixed(1) : '—'}</Text><Text style={styles.heroFoot}>توقع FantasyIQ لأفضل 5 لاعبين</Text></View>
                  <View style={styles.heroArrow}><Text style={styles.heroArrowText}>←</Text></View>
                </View>
              </View>

              <View style={styles.metricsCard}>
                <Metric title="اللاعبون" value={overview ? String(overview.player_count) : '—'} />
                <View style={styles.metricDivider} />
                <Metric title="المتاحون" value={overview ? String(overview.available_count) : '—'} accent={C.mint} />
                <View style={styles.metricDivider} />
                <Metric title="الأندية" value={overview ? String(overview.club_count) : '—'} accent={C.blue} />
              </View>

              <SectionHeading title="ترشيحات الجولة" subtitle={overview?.model_ready ? `توقع FantasyIQ · GW ${overview.prediction_gameweek}` : 'توقعات FPL المنشورة'} action="كل اللاعبين" onAction={() => router.push('/players')} />
              <View style={styles.card}>
                {topPlayers.slice(0, 4).map((player, index) => <PlayerRow key={player.id} player={player} rank={index + 1} />)}
                {!topPlayers.length && <EmptyText>ستظهر الترشيحات بعد اتصال الخادم.</EmptyText>}
              </View>
              <Text style={styles.disclaimer}>التوقعات إرشادية وقد تختلف عن النقاط الفعلية. عند غياب تاريخ مناسب نعرض توقع FPL.</Text>
            </>
          )}

          {tab === 'اللاعبون' && (
            <>
              <Label color={C.mint}>استكشف السوق</Label>
              <Text style={styles.screenTitle}>اللاعبون</Text>
              <View style={styles.searchBox}><Text style={styles.searchIcon}>⌕</Text><TextInput value={query} onChangeText={setQuery} placeholder="ابحث عن لاعب أو نادٍ" placeholderTextColor="#71869D" style={styles.searchInput} textAlign="right" /></View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
                {positions.map((position) => {
                  const active = positionFilter === position;
                  return <Pressable key={position} onPress={() => setPositionFilter(position)} style={[styles.chip, active && styles.chipActive]}><Text style={[styles.chipText, active && styles.chipTextActive]}>{positionNames[position]}</Text></Pressable>;
                })}
              </ScrollView>
              <View style={styles.listHeader}><Label>{filteredPlayers.length} لاعب</Label><Label color={C.lime}>xP الجولة ↓</Label></View>
              <Pressable onPress={() => void loadProfiles()} style={styles.profileButton}><Text style={styles.optimizeText}>{loadingProfiles ? 'نحمّل التحليل…' : 'تحليل مجموعات اللاعبين والحالات الشاذة'}</Text></Pressable>
              {profiles && <View style={styles.planCard}><Text style={styles.sectionTitle}>تحليل موسم {profiles.metrics.source_season}</Text><Text style={styles.playerMeta}>{profiles.metrics.clusters} مجموعات · Silhouette {profiles.metrics.silhouette_score} · {profiles.metrics.anomaly_count} حالات شاذة</Text>{profiles.players.slice(0, 10).map((p) => <Text key={`profile-${p.id}`} style={styles.playerMeta}>{p.player} · مجموعة {p.cluster + 1}{p.is_anomaly ? ' · حالة غير معتادة' : ''} · درجة {p.anomaly_score.toFixed(2)}</Text>)}<Text style={styles.disclaimer}>تحليل وصفي لنهاية الموسم، وليس توقعًا للجولة أو دلالة على إصابة.</Text></View>}
              <Text style={styles.transferTitle}>توصيات الانتقالات</Text>
              <Text style={styles.disclaimer}>اختر لاعبًا لعرض أفضل البدائل من مركزه.</Text>
              <View style={styles.transferBudgetRow}>
                <Label>الزيادة المتاحة فوق سعر اللاعب</Label>
                <View style={styles.budgetNudges}>
                  <Pressable onPress={() => setTransferBudget((value) => Math.max(0, Number((value - 0.5).toFixed(1))))} style={styles.budgetAdjust}><Text style={styles.adjustText}>−</Text></Pressable>
                  <Text style={styles.transferBudgetValue}>£{transferBudget.toFixed(1)}m</Text>
                  <Pressable onPress={() => setTransferBudget((value) => Math.min(20, Number((value + 0.5).toFixed(1))))} style={styles.budgetAdjust}><Text style={styles.adjustText}>+</Text></Pressable>
                </View>
              </View>
              <View style={styles.transferBudgetRow}>
                <Label>الانتقالات المجانية</Label>
                <View style={styles.budgetNudges}>
                  <Pressable onPress={() => setFreeTransfers((value) => Math.max(1, value - 1))} style={styles.budgetAdjust}><Text style={styles.adjustText}>−</Text></Pressable>
                  <Text style={styles.transferBudgetValue}>{freeTransfers}</Text>
                  <Pressable onPress={() => setFreeTransfers((value) => Math.min(5, value + 1))} style={styles.budgetAdjust}><Text style={styles.adjustText}>+</Text></Pressable>
                </View>
              </View>
              <View style={styles.transferBudgetRow}>
                <Label>انتقالات عليها خصم</Label>
                <View style={styles.budgetNudges}>
                  <Pressable onPress={() => setHitPoints((value) => Math.max(0, value - 4))} style={styles.budgetAdjust}><Text style={styles.adjustText}>−</Text></Pressable>
                  <Text style={styles.transferBudgetValue}>{hitPoints} · −{hitPoints * 4} نقطة</Text>
                  <Pressable onPress={() => setHitPoints((value) => Math.min(20, value + 4))} style={styles.budgetAdjust}><Text style={styles.adjustText}>+</Text></Pressable>
                </View>
              </View>
              <View style={[styles.card, { marginBottom: 14 }]}>
                {filteredPlayers.slice(0, 80).map((player) => (
                  <Pressable key={`transfer-${player.id}`} onPress={() => void findTransfers(player)} style={[styles.transferPickRow, selectedPlayerId === player.id && styles.transferPickActive]}>
                    <Text style={styles.transferSelect}>{selectedPlayerId === player.id ? 'محدد' : 'اختر'}</Text>
                    <Text style={styles.playerName}>{player.player}</Text>
                    <Text style={styles.playerMeta}>{player.position} · £{player.cost_m.toFixed(1)}m</Text>
                  </Pressable>
                ))}
              </View>
              {loadingTransfers && <ActivityIndicator color={C.lime} style={{ marginVertical: 16 }} />}
              {transferAdvice && (
                <>
                  <SectionHeading title={`بدائل ${transferAdvice.current_player.player}`} subtitle={`نقاطه المتوقعة ${transferAdvice.current_projection.toFixed(1)} · GW ${transferAdvice.prediction_gameweek ?? '—'}`} />
                  <View style={styles.card}>
                    {transferAdvice.recommendations.map((player) => (
                      <View key={`advice-${player.id}`} style={styles.adviceRow}>
                        <View style={styles.adviceMain}>
                          <Text style={styles.playerName}>{player.player}</Text>
                          <Text style={styles.playerMeta}>{player.team_name} · £{player.cost_m.toFixed(1)}m ({player.price_difference >= 0 ? '+' : ''}{player.price_difference.toFixed(1)})</Text>
                          {(player.high_potential_probability ?? 0) >= 0.65 && <Text style={styles.potentialBadge}>مرشح قوي · {Math.round(player.high_potential_probability! * 100)}%</Text>}
                        </View>
                        <View style={styles.adviceNumbers}>
                          <Text style={styles.playerXp}>{player.expected_points.toFixed(1)} نقطة</Text>
                          <Text style={[styles.playerMeta, { color: player.net_points_gain >= 0 ? C.mint : C.coral }]}>{player.net_points_gain >= 0 ? '+' : ''}{player.net_points_gain.toFixed(1)} صافي النقاط</Text>
                          {player.transfer_cost > 0 && <Text style={[styles.playerMeta, { color: C.coral }]}>الخصم: −{player.transfer_cost}</Text>}
                        </View>
                      </View>
                    ))}
                    {!transferAdvice.recommendations.length && <EmptyText>لا توجد بدائل مناسبة بهذه الميزانية.</EmptyText>}
                  </View>
                  <Text style={styles.disclaimer}>صافي المكسب = فرق توقع النقاط − الخصم المحدد. الانتقال المجاني يُستخدم أولًا؛ لا يُحتسب خصم إضافي إلا إذا تجاوزت الانتقالات الحرة أو أدخلت Hits.</Text>
                </>
              )}
              <View style={styles.card}>
                {filteredPlayers.slice(0, 80).map((player) => <PlayerRow key={player.id} player={player} />)}
                {!filteredPlayers.length && <EmptyText>لا توجد نتائج مطابقة.</EmptyText>}
              </View>
              {filteredPlayers.length > 80 && <Text style={styles.disclaimer}>اعرض أول 80 نتيجة. استخدم البحث للوصول إلى لاعب محدد.</Text>}
            </>
          )}

          {tab === 'فريقي' && (
            <>
              <Label color={C.mint}>مخطط الفريق</Label>
              <Text style={styles.screenTitle}>ابنِ تشكيلتك</Text>
              <View style={styles.card}>
                <Text style={styles.transferTitle}>استيراد فريقك من FPL</Text>
                <Text style={styles.disclaimer}>أدخل رقم الفريق الموجود في رابط صفحة فريقك العامة. لا نطلب كلمة المرور.</Text>
                <View style={styles.searchBox}><TextInput value={entryId} onChangeText={setEntryId} keyboardType="number-pad" placeholder="رقم فريق FPL" placeholderTextColor="#71869D" style={styles.searchInput} textAlign="right" /></View>
                <Pressable onPress={() => void importFplTeam()} disabled={importingTeam} style={[styles.optimizeButton, importingTeam && { opacity: 0.65 }]}>{importingTeam ? <ActivityIndicator color={C.bg} /> : <Text style={styles.optimizeText}>استيراد التشكيلة</Text>}</Pressable>
                {importedTeam && <Text style={[styles.playerMeta, { marginTop: 10 }]}>تم استيراد {importedTeam.team_name} · GW {importedTeam.event} · الرصيد £{importedTeam.bank.toFixed(1)}m</Text>}
              </View>
              <View style={styles.budgetCard}>
                <View style={styles.budgetTop}><View><Label>ميزانية الفريق</Label><Text style={styles.budgetValue}>£{budget.toFixed(1)}m</Text></View><View style={styles.budgetIcon}><Text>◈</Text></View></View>
                <View style={styles.budgetControls}>
                  <Pressable onPress={() => setBudget((value) => Math.max(80, Number((value - 0.5).toFixed(1))))} style={styles.budgetAdjust}><Text style={styles.adjustText}>−</Text></Pressable>
                  <View style={styles.budgetTrack}><View style={[styles.budgetFill, { width: `${((budget - 80) / 40) * 100}%` }]} /></View>
                  <Pressable onPress={() => setBudget((value) => Math.min(120, Number((value + 0.5).toFixed(1))))} style={styles.budgetAdjust}><Text style={styles.adjustText}>+</Text></Pressable>
                </View>
                <View style={styles.budgetLimits}><Text style={styles.budgetLimitText}>£80m</Text><Text style={styles.budgetLimitText}>£120m</Text></View>
              </View>

              <Pressable onPress={() => void runOptimizer()} disabled={optimizing} style={[styles.optimizeButton, optimizing && { opacity: 0.7 }]}>
                {optimizing ? <ActivityIndicator color={C.bg} /> : <Text style={styles.optimizeGlyph}>✦</Text>}
                <Text style={styles.optimizeText}>{optimizing ? 'نبحث عن أفضل تشكيلة…' : 'اقترح أفضل تشكيلة'}</Text>
              </Pressable>

              {(importedTeam || squad) ? (
                <>
                  {importedTeam ? <View style={styles.metricsCard}><Metric title="الفريق" value={importedTeam.team_name} accent={C.lime} /><View style={styles.metricDivider} /><Metric title="الرصيد" value={`£${importedTeam.bank.toFixed(1)}m`} accent={C.mint} /><View style={styles.metricDivider} /><Metric title="الجولة" value={String(importedTeam.event)} accent={C.blue} /></View> : null}
                  {squad && !importedTeam ? <View style={styles.metricsCard}>
                    <Metric title="قيمة الفريق" value={`£${squad.cost.toFixed(1)}m`} accent={C.lime} />
                    <View style={styles.metricDivider} />
                    <Metric title="المتبقي" value={`£${squad.remaining_budget.toFixed(1)}m`} accent={C.mint} />
                    <View style={styles.metricDivider} />
                    <Metric title="مجموع التوقع" value={squad.combined_fantasyiq_projection.toFixed(1)} accent={C.blue} />
                  </View> : null}
                  <SectionHeading title={importedTeam ? `فريق ${importedTeam.team_name}` : 'تشكيلتك المقترحة'} subtitle="حدد حتى 5 لاعبين للاستبدال" />
                  {importedTeam && <View style={styles.transferBudgetRow}><Label>الانتقالات المجانية المتاحة</Label><Text style={styles.transferBudgetValue}>{importedTeam.free_transfers}</Text></View>}
                  <View style={styles.card}>{(importedTeam?.players ?? squad?.players ?? []).map((player) => <Pressable key={player.id} onPress={() => setSelectedOutgoingIds((ids) => ids.includes(player.id) ? ids.filter((id) => id !== player.id) : ids.length < 5 ? [...ids, player.id] : ids)} style={[styles.transferPickRow, selectedOutgoingIds.includes(player.id) && styles.transferPickActive]}><Text style={styles.transferSelect}>{selectedOutgoingIds.includes(player.id) ? 'استبدال' : 'حدد'}</Text><PlayerRow player={player} /></Pressable>)}</View>
                  <Pressable onPress={() => void buildTransferPlan()} disabled={planningTransfers || !selectedOutgoingIds.length} style={[styles.optimizeButton, (!selectedOutgoingIds.length || planningTransfers) && { opacity: 0.6 }]}>{planningTransfers ? <ActivityIndicator color={C.bg} /> : <Text style={styles.optimizeGlyph}>↔</Text>}<Text style={styles.optimizeText}>{planningTransfers ? 'نحسب أفضل خطة…' : `احسب خطة الاستبدال (${selectedOutgoingIds.length})`}</Text></Pressable>
                  {transferPlans.map((plan, index) => <View key={`plan-${index}`} style={styles.planCard}><Text style={styles.sectionTitle}>الخطة {index + 1} · صافي {plan.net_points_gain > 0 ? '+' : ''}{plan.net_points_gain.toFixed(1)} نقطة</Text><Text style={styles.playerMeta}>خصم −{plan.hit_points} · فارق السعر {plan.cost_delta > 0 ? '+' : ''}£{plan.cost_delta.toFixed(1)}m · المتبقي £{plan.remaining_bank.toFixed(1)}m</Text>{plan.replacements.map((move) => <Text key={`${move.out.id}-${move.in.id}`} style={styles.playerMeta}>{move.out.player} ← {move.in.player} ({move.points_gain > 0 ? '+' : ''}{move.points_gain.toFixed(1)})</Text>)}</View>)}
                  {squad && !importedTeam && <Text style={styles.disclaimer}>تشكيلة مقترحة وليست مستوردة من حساب FPL.</Text>}
                </>
              ) : (
                <View style={styles.squadPlaceholder}><Text style={styles.placeholderIcon}>♙</Text><Text style={styles.placeholderTitle}>تشكيلتك في انتظارك</Text><Text style={styles.placeholderBody}>نختار 15 لاعبًا حسب المراكز والميزانية، ونوازن بين توقعات الجولة وقيود الأندية.</Text></View>
              )}
            </>
          )}
        </ScrollView>
      )}

      <View style={styles.tabBar}>
        {([
          { name: 'الرئيسية' as Tab, icon: '⌂', href: '/' as Href },
          { name: 'اللاعبون' as Tab, icon: '◉', href: '/players' as Href },
          { name: 'فريقي' as Tab, icon: '♙', href: '/squad' as Href },
        ]).map((item) => {
          const active = tab === item.name;
          return <Pressable key={item.name} onPress={() => router.navigate(item.href)} style={styles.tabButton}><Text style={[styles.tabIcon, active && styles.tabIconActive]}>{item.icon}</Text><Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{item.name}</Text>{active && <View style={styles.tabIndicator} />}</Pressable>;
        })}
      </View>
    </SafeAreaView>
  );
}

function SectionHeading({ title, subtitle, action, onAction }: { title: string; subtitle: string; action?: string; onAction?: () => void }) {
  return <View style={styles.sectionHeading}><View><Text style={styles.sectionTitle}>{title}</Text><Text style={styles.sectionSub}>{subtitle}</Text></View>{action && <Pressable onPress={onAction}><Text style={styles.sectionAction}>{action}  ‹</Text></Pressable>}</View>;
}

function EmptyText({ children }: { children: React.ReactNode }) {
  return <Text style={styles.emptyText}>{children}</Text>;
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: C.bg },
  topBar: { height: 68, paddingHorizontal: 22, flexDirection: 'row-reverse', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#142438' },
  brandMark: { width: 38, height: 38, borderRadius: 13, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  brandBall: { fontSize: 19 }, brandText: { flex: 1, alignItems: 'flex-end' },
  brandName: { color: C.text, fontSize: 14, fontWeight: '900', letterSpacing: 1.4 },
  brandSub: { color: C.muted, fontSize: 10, marginTop: 2 },
  refreshButton: { width: 38, height: 38, borderRadius: 13, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center' },
  refreshGlyph: { color: C.lime, fontSize: 23, lineHeight: 26 },
  content: { flex: 1 }, contentInner: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 30 },
  welcomeRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 18 },
  label: { fontSize: 11, fontWeight: '600', textAlign: 'right' },
  screenTitle: { color: C.text, fontSize: 26, fontWeight: '800', textAlign: 'right', marginTop: 4, letterSpacing: -0.3 },
  livePill: { flexDirection: 'row-reverse', alignItems: 'center', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#15332F' },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.mint, marginLeft: 6 }, liveText: { color: C.mint, fontSize: 10, fontWeight: '700' },
  heroCard: { minHeight: 195, backgroundColor: '#14243A', borderRadius: 24, padding: 21, overflow: 'hidden', borderWidth: 1, borderColor: '#253B56' },
  heroDecor: { position: 'absolute', width: 210, height: 210, borderRadius: 110, top: -104, left: -62, backgroundColor: '#1D3650', opacity: 0.55 },
  heroTop: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'flex-start' },
  heroEyebrow: { color: '#B9C7D5', textAlign: 'right', fontSize: 12 }, heroGw: { color: C.text, textAlign: 'right', fontSize: 31, fontWeight: '900', marginTop: 5 },
  heroIcon: { color: C.lime, fontSize: 24 }, heroDivider: { height: 1, backgroundColor: '#34495F', marginVertical: 14 },
  heroBottom: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' },
  heroBig: { color: C.lime, fontSize: 27, fontWeight: '900', textAlign: 'right' }, heroFoot: { color: '#B9C7D5', fontSize: 10, marginTop: 3, textAlign: 'right' },
  heroArrow: { width: 37, height: 37, borderRadius: 13, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center' }, heroArrowText: { color: C.bg, fontSize: 23, fontWeight: '700' },
  metricsCard: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-around', backgroundColor: C.panel, borderRadius: 18, paddingVertical: 17, marginTop: 14, borderWidth: 1, borderColor: '#192B40' },
  metric: { flex: 1, alignItems: 'center' }, metricValue: { fontSize: 19, fontWeight: '800', marginTop: 6 }, metricDivider: { width: 1, height: 31, backgroundColor: C.line },
  sectionHeading: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginTop: 26, marginBottom: 12 },
  sectionTitle: { color: C.text, textAlign: 'right', fontSize: 17, fontWeight: '800' }, sectionSub: { color: C.muted, textAlign: 'right', fontSize: 10, marginTop: 4 },
  sectionAction: { color: C.lime, fontSize: 11, fontWeight: '700' },
  card: { backgroundColor: C.panel, borderRadius: 18, paddingHorizontal: 14, borderWidth: 1, borderColor: '#192B40' },
  playerRow: { minHeight: 68, flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#1A2B3D' },
  playerIdentity: { flexDirection: 'row-reverse', alignItems: 'center', flex: 1, marginLeft: 8 },
  rank: { width: 21, textAlign: 'right', color: '#678099', fontSize: 10, fontWeight: '700', marginLeft: 8 },
  avatar: { width: 36, height: 36, borderRadius: 12, backgroundColor: '#1D3046', alignItems: 'center', justifyContent: 'center', marginLeft: 9 },
  avatarText: { color: C.mint, fontSize: 16, fontWeight: '800' }, playerCopy: { flex: 1, alignItems: 'flex-end' },
  playerName: { maxWidth: '100%', color: C.text, fontSize: 12, fontWeight: '700', textAlign: 'right' },
  playerMeta: { color: C.muted, fontSize: 10, marginTop: 4, textAlign: 'right' },
  potentialBadge: { color: C.lime, fontSize: 9, fontWeight: '800', textAlign: 'right', marginTop: 3 },
  transferTitle: { color: C.text, fontSize: 15, fontWeight: '800', textAlign: 'right', marginTop: 20 },
  profileButton: { minHeight: 44, borderRadius: 14, backgroundColor: C.panel2, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center', marginTop: 16 },
  transferBudgetRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginVertical: 12 },
  budgetNudges: { flexDirection: 'row', alignItems: 'center', gap: 8 }, transferBudgetValue: { color: C.lime, fontSize: 12, fontWeight: '800' },
  transferPickRow: { minHeight: 57, justifyContent: 'center', alignItems: 'flex-end', borderBottomWidth: 1, borderBottomColor: '#1A2B3D', paddingVertical: 7 },
  transferPickActive: { backgroundColor: '#15283A' }, transferSelect: { position: 'absolute', left: 2, color: C.mint, fontSize: 9, fontWeight: '700' },
  adviceRow: { minHeight: 68, flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#1A2B3D' },
  planCard: { backgroundColor: C.panel2, borderRadius: 16, padding: 14, marginTop: 12, borderWidth: 1, borderColor: C.line, gap: 6 },
  adviceMain: { flex: 1, alignItems: 'flex-end', marginLeft: 8 }, adviceNumbers: { minWidth: 86, alignItems: 'flex-end' },
  playerNumbers: { minWidth: 43, alignItems: 'flex-end' }, playerXp: { color: C.lime, fontWeight: '900', fontSize: 14 }, playerPrice: { color: C.muted, fontSize: 9, marginTop: 4 },
  disclaimer: { color: '#71869A', fontSize: 10, lineHeight: 16, textAlign: 'right', marginTop: 10, paddingHorizontal: 3 },
  searchBox: { minHeight: 48, borderRadius: 15, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, flexDirection: 'row-reverse', alignItems: 'center', paddingHorizontal: 13, marginTop: 18 },
  searchIcon: { color: C.mint, fontSize: 23, marginLeft: 8, marginTop: -2 }, searchInput: { flex: 1, color: C.text, fontSize: 12 },
  chips: { flexDirection: 'row-reverse', paddingVertical: 15, gap: 8 },
  chip: { borderRadius: 18, paddingVertical: 8, paddingHorizontal: 14, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line },
  chipActive: { backgroundColor: C.lime, borderColor: C.lime }, chipText: { color: C.muted, fontSize: 11, fontWeight: '700' }, chipTextActive: { color: C.bg },
  listHeader: { flexDirection: 'row-reverse', justifyContent: 'space-between', marginBottom: 8, marginTop: 3 },
  budgetCard: { backgroundColor: C.panel, borderRadius: 20, padding: 18, marginTop: 19, borderWidth: 1, borderColor: C.line },
  budgetTop: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' }, budgetValue: { color: C.text, fontSize: 25, fontWeight: '900', textAlign: 'right', marginTop: 5 },
  budgetIcon: { width: 40, height: 40, borderRadius: 14, backgroundColor: '#273A25', alignItems: 'center', justifyContent: 'center' }, budgetIconText: { color: C.lime },
  budgetControls: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 18 }, budgetAdjust: { width: 31, height: 31, borderRadius: 10, backgroundColor: C.panel2, alignItems: 'center', justifyContent: 'center' },
  adjustText: { color: C.text, fontSize: 19, fontWeight: '600', lineHeight: 22 }, budgetTrack: { flex: 1, height: 6, borderRadius: 5, backgroundColor: '#293B4F', overflow: 'hidden' }, budgetFill: { height: 6, backgroundColor: C.lime, borderRadius: 5 },
  budgetLimits: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 7 }, budgetLimitText: { color: '#73879A', fontSize: 9 },
  optimizeButton: { minHeight: 52, borderRadius: 16, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 9, marginTop: 13 },
  optimizeGlyph: { color: C.bg, fontSize: 17 }, optimizeText: { color: C.bg, fontSize: 13, fontWeight: '900' },
  squadPlaceholder: { borderRadius: 20, borderWidth: 1, borderStyle: 'dashed', borderColor: '#2C4055', alignItems: 'center', padding: 25, marginTop: 23 },
  placeholderIcon: { color: '#627A91', fontSize: 29 }, placeholderTitle: { color: C.text, fontSize: 14, fontWeight: '800', marginTop: 9 }, placeholderBody: { color: C.muted, fontSize: 11, lineHeight: 18, textAlign: 'center', marginTop: 7 },
  tabBar: { minHeight: 67, backgroundColor: '#0C1827', borderTopWidth: 1, borderTopColor: '#192A3C', flexDirection: 'row-reverse', paddingHorizontal: 18, paddingBottom: 4 },
  tabButton: { flex: 1, alignItems: 'center', justifyContent: 'center', position: 'relative', gap: 2 }, tabIcon: { color: '#698098', fontSize: 20, height: 24 }, tabIconActive: { color: C.lime }, tabLabel: { color: '#71869A', fontSize: 9, fontWeight: '600' }, tabLabelActive: { color: C.text },
  tabIndicator: { position: 'absolute', top: 0, height: 2, width: 20, borderRadius: 2, backgroundColor: C.lime },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 }, loadingText: { color: C.muted, fontSize: 12 },
  errorCard: { margin: 18, marginBottom: 0, padding: 15, backgroundColor: '#34201F', borderColor: '#724039', borderWidth: 1, borderRadius: 16 },
  errorTitle: { color: '#FFC0B6', fontWeight: '800', textAlign: 'right', fontSize: 13 }, errorBody: { color: C.text, textAlign: 'right', fontSize: 11, marginTop: 6 }, errorHint: { color: '#D5A49D', textAlign: 'right', fontSize: 10, lineHeight: 16, marginTop: 6 },
  retryButton: { alignSelf: 'flex-end', marginTop: 11, borderRadius: 10, backgroundColor: '#63372F', paddingVertical: 7, paddingHorizontal: 12 }, retryText: { color: C.text, fontSize: 10, fontWeight: '700' },
  emptyText: { color: C.muted, fontSize: 11, textAlign: 'right', paddingVertical: 18 },
});
