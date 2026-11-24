import { StatusBar } from 'expo-status-bar';
import { router, type Href } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Image,
  PanResponder,
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
  bg: '#F1F0EA', panel: '#FFFFFF', panel2: '#F7F7F3', line: '#E3E2DB',
  text: '#242723', muted: '#797E76', lime: '#BDEB43', mint: '#318365',
  blue: '#6484A1', coral: '#D87362', amber: '#C99B4A',
};

type Player = {
  id: number; player: string; position: string; team_name: string; cost_m: number;
  expected_points: number; total_points: number; points_per_game: number;
  minutes: number; form: number; selected_by_percent: number; status: string;
  photo?: string; code?: number; is_captain?: boolean; is_vice_captain?: boolean; squad_order?: number;
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
type ImportedTeam = { entry_id: number; team_name: string; manager: string; event: number; bank: number; free_transfers: number; captain_id?: number; vice_captain_id?: number; players: Player[] };
type ProfileResponse = { metrics: { clusters: number; silhouette_score: number; source_season: string; anomaly_count: number }; players: (Player & { cluster: number; anomaly_score: number; is_anomaly: boolean })[]; count: number };
type TransferPolicyReport = { folds: { training_seasons: string[]; test_season: string; rl: { points: number; transfers: number }; projection_heuristic: { points: number; transfers: number }; hold_initial_team: { points: number; transfers: number } }[]; caveats: string[] };
type RecommenderEvaluation = { test_season: string; sampled_queries: number; candidate_pool_mean_actual_points: number; methods: { hybrid: { mean_actual_points_at_5: number; share_of_top5_scoring_4plus: number; queries: number }; form_only: { mean_actual_points_at_5: number; share_of_top5_scoring_4plus: number; queries: number } }; caveat: string };
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

function PlayerPortrait({ player, size = 36 }: { player: Player; size?: number }) {
  const [failed, setFailed] = useState(false);
  const photoCode = player.photo?.replace(/\.jpg$/i, '') || (player.code ? String(player.code) : '');
  const imageUrl = photoCode ? `https://resources.premierleague.com/premierleague/photos/players/110x140/p${photoCode}.png` : '';
  return (
    <View style={[styles.portraitFrame, { width: size, height: size, borderRadius: size * 0.34 }]}>
      {imageUrl && !failed ? (
        <Image source={{ uri: imageUrl }} onError={() => setFailed(true)} resizeMode="cover" style={{ width: size, height: size }} />
      ) : (
        <Text style={{ fontSize: size * 0.52 }}>⚽</Text>
      )}
    </View>
  );
}

function BudgetSlider({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const width = useRef(1);
  const updateFromX = useCallback((x: number) => {
    const ratio = Math.max(0, Math.min(1, x / width.current));
    onChange(Math.max(80, Math.min(120, Math.round((80 + ratio * 40) * 2) / 2)));
  }, [onChange]);
  const pan = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (event) => updateFromX(event.nativeEvent.locationX),
    onPanResponderMove: (event) => updateFromX(event.nativeEvent.locationX),
  }), [updateFromX]);
  const progress = (value - 80) / 40;
  return (
    <View
      onLayout={(event) => { width.current = Math.max(event.nativeEvent.layout.width, 1); }}
      {...pan.panHandlers}
      accessibilityRole="adjustable"
      accessibilityLabel="ميزانية الفريق"
      accessibilityValue={{ min: 80, max: 120, now: value }}
      style={styles.budgetSliderTouch}
    >
      <View pointerEvents="none" style={styles.budgetTrack}><View style={[styles.budgetFill, { width: `${progress * 100}%` }]} /></View>
      <View pointerEvents="none" style={[styles.budgetThumb, { left: `${progress * 100}%` }]} />
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
        <PlayerPortrait player={player} />
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

function PitchBoard({ players, selectedIds, onSelect, captainId, viceCaptainId }: { players: Player[]; selectedIds: number[]; onSelect: (id: number) => void; captainId?: number; viceCaptainId?: number }) {
  const lines = [
    { position: 'Forward', label: 'الهجوم' },
    { position: 'Midfielder', label: 'الوسط' },
    { position: 'Defender', label: 'الدفاع' },
    { position: 'Goalkeeper', label: 'الحراسة' },
  ];
  return (
    <View style={styles.pitchCard}>
      <View style={styles.pitchHeader}>
        <View style={styles.pitchCount}><Text style={styles.pitchCountText}>{players.length} لاعب</Text></View>
        <View><Text style={styles.pitchTitle}>خطة الفريق</Text><Text style={styles.pitchSubtitle}>اضغط على لاعب لتحديده للاستبدال</Text></View>
      </View>
      <View style={styles.pitchField}>
        <View pointerEvents="none" style={styles.pitchOutline}>
          <View style={styles.pitchHalfLine} />
          <View style={styles.pitchCenterCircle} />
          <View style={styles.pitchBoxTop} />
          <View style={styles.pitchBoxBottom} />
        </View>
        {lines.map((line) => {
          const linePlayers = players.filter((player) => player.position === line.position);
          if (!linePlayers.length) return null;
          return (
            <View key={line.position} style={styles.pitchLine}>
              <Text style={styles.pitchLineLabel}>{line.label}</Text>
              <View style={styles.pitchPlayerRow}>
                {linePlayers.map((player) => {
                  const selected = selectedIds.includes(player.id);
                  const prediction = player.fantasyiq_points ?? player.expected_points;
                  return (
                    <Pressable key={player.id} onPress={() => onSelect(player.id)} accessibilityRole="button" accessibilityLabel={`${selected ? 'إلغاء تحديد' : 'تحديد'} ${player.player} للاستبدال`} style={({ pressed }) => [styles.pitchPlayer, pressed && styles.pressedPlayer]}>
                      <Animated.View style={[styles.pitchPortrait, selected && styles.pitchPortraitSelected, { transform: [{ scale: selected ? 1.08 : 1 }] }]}>
                        <PlayerPortrait player={player} size={36} />
                        {selected && <View style={styles.pitchSwapBadge}><Text style={styles.pitchSwapText}>↔</Text></View>}
                        {(player.id === captainId || player.id === viceCaptainId) && <View style={styles.captainBadge}><Text style={styles.captainBadgeText}>{player.id === captainId ? 'C' : 'V'}</Text></View>}
                      </Animated.View>
                      <Text numberOfLines={1} style={[styles.pitchPlayerName, selected && styles.pitchPlayerNameSelected]}>{player.player.split(' ').slice(-1)[0]}</Text>
                      <Text style={styles.pitchPlayerPoints}>{Number(prediction || 0).toFixed(1)} xp · £{player.cost_m.toFixed(1)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          );
        })}
      </View>
      <View style={styles.pitchLegend}><View style={styles.pitchLegendMark} /><Text style={styles.pitchLegendText}>اللاعب المحدد للاستبدال</Text></View>
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
  const [transferSelectionMessage, setTransferSelectionMessage] = useState('');
  const [transferPlans, setTransferPlans] = useState<TransferPlan[]>([]);
  const [planBank, setPlanBank] = useState(0);
  const [planningTransfers, setPlanningTransfers] = useState(false);
  const [entryId, setEntryId] = useState('');
  const [importedTeam, setImportedTeam] = useState<ImportedTeam | null>(null);
  const [importingTeam, setImportingTeam] = useState(false);
  const [profiles, setProfiles] = useState<ProfileResponse | null>(null);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [policyReport, setPolicyReport] = useState<TransferPolicyReport | null>(null);
  const [recommenderEvaluation, setRecommenderEvaluation] = useState<RecommenderEvaluation | null>(null);
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
    const selectedPlayers = activeSquad.players.filter((player) => selectedOutgoingIds.includes(player.id));
    if (new Set(selectedPlayers.map((player) => player.position)).size !== selectedPlayers.length) {
      setTransferSelectionMessage('اختَر لاعبًا واحدًا فقط من كل مركز. ألغِ تحديد اللاعب البرتقالي قبل اختيار لاعب آخر من المركز نفسه.');
      return;
    }
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
      setImportedTeam(result); setSelectedOutgoingIds([]); setTransferSelectionMessage(''); setTransferPlans([]); setPlanBank(result.bank); setFreeTransfers(result.free_transfers); setError('');
    } catch (err) { setError(err instanceof Error ? err.message : 'تعذّر استيراد فريق FPL'); }
    finally { setImportingTeam(false); }
  };

  const loadProfiles = async () => {
    setLoadingProfiles(true);
    try { setProfiles(await api<ProfileResponse>('/api/analytics/player-profiles?limit=30')); }
    catch (err) { setError(err instanceof Error ? err.message : 'تعذّر تحميل تحليل اللاعبين'); }
    finally { setLoadingProfiles(false); }
  };

  const loadPolicyReport = async () => {
    try { setPolicyReport(await api<TransferPolicyReport>('/api/analytics/transfer-policy')); }
    catch (err) { setError(err instanceof Error ? err.message : 'تعذّر تحميل تقييم الانتقالات'); }
  };

  const loadRecommenderEvaluation = async () => {
    try { setRecommenderEvaluation(await api<RecommenderEvaluation>('/api/analytics/recommender-evaluation')); }
    catch (err) { setError(err instanceof Error ? err.message : 'تعذّر تحميل تقييم التوصيات'); }
  };

  const positions = ['الكل', 'Goalkeeper', 'Defender', 'Midfielder', 'Forward'];
  const positionNames: Record<string, string> = {
    الكل: 'الكل', Goalkeeper: 'حارس', Defender: 'دفاع', Midfielder: 'وسط', Forward: 'هجوم',
  };
  const activeTeamPlayers = importedTeam?.players ?? squad?.players ?? [];
  const toggleOutgoingPlayer = (id: number) => {
    const target = activeTeamPlayers.find((player) => player.id === id);
    if (!target) return;
    if (selectedOutgoingIds.includes(id)) {
      setSelectedOutgoingIds((ids) => ids.filter((selectedId) => selectedId !== id));
      setTransferSelectionMessage('');
      return;
    }
    const samePositionAlreadySelected = activeTeamPlayers.some((player) => selectedOutgoingIds.includes(player.id) && player.position === target.position);
    if (samePositionAlreadySelected) {
      setTransferSelectionMessage(`ألغِ تحديد اللاعب البرتقالي من مركز ${positionNames[target.position] ?? target.position} قبل اختيار لاعب آخر من المركز نفسه.`);
      return;
    }
    if (selectedOutgoingIds.length >= 5) {
      setTransferSelectionMessage('يمكنك اختيار حتى 5 لاعبين، بحد أقصى لاعب واحد من كل مركز.');
      return;
    }
    setSelectedOutgoingIds((ids) => [...ids, id]);
    setTransferSelectionMessage('');
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
              <Pressable onPress={() => void loadRecommenderEvaluation()} style={styles.profileButton}><Text style={styles.optimizeText}>عرض تقييم نموذج التوصيات</Text></Pressable>
              {recommenderEvaluation && <View style={styles.planCard}><Text style={styles.sectionTitle}>تقييم موسم {recommenderEvaluation.test_season} · {recommenderEvaluation.sampled_queries} مقارنة</Text><Text style={styles.playerMeta}>متوسط نقاط أفضل 5: Hybrid {recommenderEvaluation.methods.hybrid.mean_actual_points_at_5.toFixed(2)} · الفورم فقط {recommenderEvaluation.methods.form_only.mean_actual_points_at_5.toFixed(2)}</Text><Text style={styles.playerMeta}>لا توجد أفضلية مثبتة لـ Hybrid؛ ترتيب الفورم ما زال أقوى في هذا الاختبار.</Text><Text style={styles.disclaimer}>{recommenderEvaluation.caveat}</Text></View>}
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
              <Pressable onPress={() => void loadPolicyReport()} style={styles.profileButton}><Text style={styles.optimizeText}>عرض تقييم وكيل الانتقالات التجريبي</Text></Pressable>
              {policyReport && <View style={styles.planCard}><Text style={styles.sectionTitle}>اختبار الوكيل زمنيًا</Text>{policyReport.folds.map((fold) => <Text key={fold.test_season} style={styles.playerMeta}>اختبار {fold.test_season}: RL {fold.rl.points} نقطة / {fold.rl.transfers} انتقال · الفورم {fold.projection_heuristic.points} · الاحتفاظ {fold.hold_initial_team.points}</Text>)}<Text style={styles.disclaimer}>{policyReport.caveats[0]}</Text></View>}
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
                  <Pressable accessibilityRole="button" accessibilityLabel="تقليل الميزانية نصف مليون" onPress={() => setBudget((value) => Math.max(80, Number((value - 0.5).toFixed(1))))} style={({ pressed }) => [styles.budgetAdjust, pressed && styles.buttonPressed]}><Text style={styles.adjustText}>−</Text></Pressable>
                  <BudgetSlider value={budget} onChange={setBudget} />
                  <Pressable accessibilityRole="button" accessibilityLabel="زيادة الميزانية نصف مليون" onPress={() => setBudget((value) => Math.min(120, Number((value + 0.5).toFixed(1))))} style={({ pressed }) => [styles.budgetAdjust, pressed && styles.buttonPressed]}><Text style={styles.adjustText}>+</Text></Pressable>
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
                  <SectionHeading title={importedTeam ? `فريق ${importedTeam.team_name}` : 'تشكيلتك المقترحة'} subtitle="اختَر لاعبًا واحدًا كحد أقصى من كل مركز" />
                  {importedTeam && <View style={styles.transferBudgetRow}><Label>الانتقالات المجانية المتاحة</Label><Text style={styles.transferBudgetValue}>{importedTeam.free_transfers}</Text></View>}
                  <PitchBoard players={activeTeamPlayers.filter((p) => p.position !== 'Bench' && (p.squad_order === undefined || p.squad_order <= 11))} selectedIds={selectedOutgoingIds} onSelect={toggleOutgoingPlayer} captainId={importedTeam?.captain_id} viceCaptainId={importedTeam?.vice_captain_id} />
                  {importedTeam && <View style={styles.benchCard}><Text style={styles.benchTitle}>الدكة · {activeTeamPlayers.filter((p) => (p.squad_order ?? 0) > 11).length} بدلاء</Text><View style={styles.benchRow}>{activeTeamPlayers.filter((p) => (p.squad_order ?? 0) > 11).map((p) => <View key={`bench-${p.id}`} style={styles.benchPlayer}><PlayerPortrait player={p} size={32}/><Text style={styles.benchName}>{p.player.split(' ').slice(-1)[0]}</Text><Text style={styles.benchPrice}>£{p.cost_m.toFixed(1)} · {p.selected_by_percent.toFixed(1)}%</Text></View>)}</View></View>}
                  {transferSelectionMessage ? <Text style={styles.pitchSelectionNotice}>{transferSelectionMessage}</Text> : null}
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
  topBar: { height: 68, paddingHorizontal: 22, flexDirection: 'row-reverse', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#18372A' },
  brandMark: { width: 38, height: 38, borderRadius: 13, backgroundColor: '#B9E95D', alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  brandBall: { fontSize: 19 }, brandText: { flex: 1, alignItems: 'flex-end' },
  brandName: { color: C.text, fontSize: 14, fontWeight: '900', letterSpacing: 1.4 },
  brandSub: { color: C.muted, fontSize: 10, marginTop: 2 },
  refreshButton: { width: 38, height: 38, borderRadius: 13, borderWidth: 1, borderColor: C.line, backgroundColor: '#10281F', alignItems: 'center', justifyContent: 'center' },
  refreshGlyph: { color: C.lime, fontSize: 23, lineHeight: 26 },
  content: { flex: 1 }, contentInner: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 30 },
  welcomeRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 18 },
  label: { fontSize: 11, fontWeight: '600', textAlign: 'right' },
  screenTitle: { color: C.text, fontSize: 26, fontWeight: '800', textAlign: 'right', marginTop: 4, letterSpacing: -0.3 },
  livePill: { flexDirection: 'row-reverse', alignItems: 'center', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#173B2D' },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.mint, marginLeft: 6 }, liveText: { color: C.mint, fontSize: 10, fontWeight: '700' },
  heroCard: { minHeight: 195, backgroundColor: '#12432F', borderRadius: 24, padding: 21, overflow: 'hidden', borderWidth: 1, borderColor: '#39714E' },
  heroDecor: { position: 'absolute', width: 210, height: 210, borderRadius: 110, top: -104, left: -62, backgroundColor: '#287249', opacity: 0.38 },
  heroTop: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'flex-start' },
  heroEyebrow: { color: '#D2E9D9', textAlign: 'right', fontSize: 12 }, heroGw: { color: C.text, textAlign: 'right', fontSize: 31, fontWeight: '900', marginTop: 5 },
  heroIcon: { color: C.lime, fontSize: 24 }, heroDivider: { height: 1, backgroundColor: '#4A815B', marginVertical: 14 },
  heroBottom: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' },
  heroBig: { color: C.lime, fontSize: 27, fontWeight: '900', textAlign: 'right' }, heroFoot: { color: '#D2E9D9', fontSize: 10, marginTop: 3, textAlign: 'right' },
  heroArrow: { width: 37, height: 37, borderRadius: 13, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center' }, heroArrowText: { color: C.bg, fontSize: 23, fontWeight: '700' },
  pitchCard: { marginTop: 16, padding: 14, borderRadius: 22, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, shadowColor: '#393B32', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 }, elevation: 2 },
  pitchHeader: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: 11 },
  pitchTitle: { color: C.text, fontSize: 14, fontWeight: '900', textAlign: 'right' }, pitchSubtitle: { color: C.muted, fontSize: 9, marginTop: 3, textAlign: 'right' },
  pitchCount: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, backgroundColor: '#F1F2EC' }, pitchCountText: { color: '#58705B', fontSize: 10, fontWeight: '800' },
  pitchField: { minHeight: 390, justifyContent: 'space-around', overflow: 'hidden', borderRadius: 16, paddingVertical: 10, backgroundColor: '#E9EFE4' },
  pitchOutline: { ...StyleSheet.absoluteFill, margin: 8, borderWidth: 1, borderColor: '#C8D2C1', borderRadius: 13, opacity: 0.9 },
  pitchHalfLine: { position: 'absolute', top: '50%', left: 0, right: 0, height: 1, backgroundColor: '#C8D2C1' },
  pitchCenterCircle: { position: 'absolute', width: 86, height: 86, borderWidth: 1, borderColor: '#C8D2C1', borderRadius: 44, left: '50%', top: '50%', marginLeft: -43, marginTop: -43 },
  pitchBoxTop: { position: 'absolute', width: '52%', height: 40, borderWidth: 1, borderColor: '#C8D2C1', borderTopWidth: 0, alignSelf: 'center', top: 0 },
  pitchBoxBottom: { position: 'absolute', width: '52%', height: 40, borderWidth: 1, borderColor: '#C8D2C1', borderBottomWidth: 0, alignSelf: 'center', bottom: 0 },
  pitchLine: { zIndex: 1, alignItems: 'center', paddingVertical: 3 }, pitchLineLabel: { color: '#677567', fontSize: 8, fontWeight: '800', marginBottom: 3 },
  pitchPlayerRow: { width: '100%', flexDirection: 'row', justifyContent: 'space-evenly', alignItems: 'flex-start', flexWrap: 'wrap', rowGap: 6 },
  pitchPlayer: { width: 62, alignItems: 'center', paddingVertical: 2 }, pressedPlayer: { opacity: 0.82 }, buttonPressed: { opacity: 0.78, transform: [{ scale: 0.96 }] },
  pitchPortrait: { width: 42, height: 42, borderRadius: 15, borderWidth: 2, borderColor: '#E8F6A0', backgroundColor: '#D8F36A', alignItems: 'center', justifyContent: 'center' },
  pitchPortraitSelected: { borderColor: '#FFB57C' }, pitchSwapBadge: { position: 'absolute', right: -5, top: -5, width: 18, height: 18, borderRadius: 9, backgroundColor: '#F3A267', alignItems: 'center', justifyContent: 'center' }, pitchSwapText: { color: '#422918', fontSize: 11, fontWeight: '900' },
  captainBadge: { position: 'absolute', left: -5, top: -5, width: 17, height: 17, borderRadius: 9, backgroundColor: '#20231F', alignItems: 'center', justifyContent: 'center' }, captainBadgeText: { color: '#C8F43D', fontSize: 9, fontWeight: '900' },
  benchCard: { marginTop: 12, padding: 12, borderRadius: 16, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E1E2DA' }, benchTitle: { color: '#20231F', textAlign: 'right', fontSize: 12, fontWeight: '800', marginBottom: 9 }, benchRow: { flexDirection: 'row-reverse', justifyContent: 'space-around', flexWrap: 'wrap', gap: 12 }, benchPlayer: { alignItems: 'center', minWidth: 54 }, benchName: { color: '#20231F', fontSize: 9, marginTop: 4 }, benchPrice: { color: '#747A72', fontSize: 8, marginTop: 2, fontVariant: ['tabular-nums'] },
  pitchPlayerName: { maxWidth: 52, color: '#30352F', fontSize: 8, fontWeight: '700', marginTop: 3 }, pitchPlayerNameSelected: { color: '#A55238' },
  pitchPlayerPoints: { color: '#6F796F', fontSize: 7, marginTop: 1, fontVariant: ['tabular-nums'] },
  pitchLegend: { flexDirection: 'row-reverse', alignItems: 'center', marginTop: 9, gap: 6 }, pitchLegendMark: { width: 9, height: 9, borderRadius: 4, backgroundColor: '#F3A267' }, pitchLegendText: { color: C.muted, fontSize: 9 },
  pitchSelectionNotice: { color: '#FFD09E', backgroundColor: '#4B3527', borderRadius: 10, paddingVertical: 8, paddingHorizontal: 11, marginTop: 9, textAlign: 'right', fontSize: 10, lineHeight: 16 },
  metricsCard: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-around', backgroundColor: C.panel, borderRadius: 18, paddingVertical: 17, marginTop: 14, borderWidth: 1, borderColor: '#244536' },
  metric: { flex: 1, alignItems: 'center' }, metricValue: { fontSize: 19, fontWeight: '800', marginTop: 6 }, metricDivider: { width: 1, height: 31, backgroundColor: C.line },
  sectionHeading: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginTop: 26, marginBottom: 12 },
  sectionTitle: { color: C.text, textAlign: 'right', fontSize: 17, fontWeight: '800' }, sectionSub: { color: C.muted, textAlign: 'right', fontSize: 10, marginTop: 4 },
  sectionAction: { color: C.lime, fontSize: 11, fontWeight: '700' },
  card: { backgroundColor: C.panel, borderRadius: 18, paddingHorizontal: 14, borderWidth: 1, borderColor: '#244536' },
  playerRow: { minHeight: 68, flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#203D2F' },
  playerIdentity: { flexDirection: 'row-reverse', alignItems: 'center', flex: 1, marginLeft: 8 },
  rank: { width: 21, textAlign: 'right', color: '#81A38F', fontSize: 10, fontWeight: '700', marginLeft: 8 },
  portraitFrame: { backgroundColor: '#203A30', borderWidth: 1, borderColor: '#496853', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', marginLeft: 9 }, playerCopy: { flex: 1, alignItems: 'flex-end' },
  playerName: { maxWidth: '100%', color: C.text, fontSize: 12, fontWeight: '700', textAlign: 'right' },
  playerMeta: { color: C.muted, fontSize: 10, marginTop: 4, textAlign: 'right' },
  potentialBadge: { color: C.lime, fontSize: 9, fontWeight: '800', textAlign: 'right', marginTop: 3 },
  transferTitle: { color: C.text, fontSize: 15, fontWeight: '800', textAlign: 'right', marginTop: 20 },
  profileButton: { minHeight: 44, borderRadius: 14, backgroundColor: C.panel2, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center', marginTop: 16 },
  transferBudgetRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginVertical: 12 },
  budgetNudges: { flexDirection: 'row', alignItems: 'center', gap: 8 }, transferBudgetValue: { color: C.lime, fontSize: 12, fontWeight: '800' },
  transferPickRow: { minHeight: 57, justifyContent: 'center', alignItems: 'flex-end', borderBottomWidth: 1, borderBottomColor: '#203D2F', paddingVertical: 7 },
  transferPickActive: { backgroundColor: '#1B3B2C' }, transferSelect: { position: 'absolute', left: 2, color: C.mint, fontSize: 9, fontWeight: '700' },
  adviceRow: { minHeight: 68, flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#203D2F' },
  planCard: { backgroundColor: C.panel2, borderRadius: 16, padding: 14, marginTop: 12, borderWidth: 1, borderColor: C.line, gap: 6 },
  adviceMain: { flex: 1, alignItems: 'flex-end', marginLeft: 8 }, adviceNumbers: { minWidth: 86, alignItems: 'flex-end' },
  playerNumbers: { minWidth: 43, alignItems: 'flex-end' }, playerXp: { color: C.lime, fontWeight: '900', fontSize: 14 }, playerPrice: { color: C.muted, fontSize: 9, marginTop: 4 },
  disclaimer: { color: '#8AA394', fontSize: 10, lineHeight: 16, textAlign: 'right', marginTop: 10, paddingHorizontal: 3 },
  searchBox: { minHeight: 48, borderRadius: 15, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, flexDirection: 'row-reverse', alignItems: 'center', paddingHorizontal: 13, marginTop: 18 },
  searchIcon: { color: C.mint, fontSize: 23, marginLeft: 8, marginTop: -2 }, searchInput: { flex: 1, color: C.text, fontSize: 12 },
  chips: { flexDirection: 'row-reverse', paddingVertical: 15, gap: 8 },
  chip: { borderRadius: 12, paddingVertical: 9, paddingHorizontal: 15, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E1E2DB' },
  chipActive: { backgroundColor: '#242723', borderColor: '#242723' }, chipText: { color: '#747A72', fontSize: 11, fontWeight: '700' }, chipTextActive: { color: '#FFFFFF' },
  listHeader: { flexDirection: 'row-reverse', justifyContent: 'space-between', marginBottom: 8, marginTop: 3 },
  budgetCard: { backgroundColor: C.panel, borderRadius: 20, padding: 18, marginTop: 19, borderWidth: 1, borderColor: C.line, shadowColor: '#393B32', shadowOpacity: 0.05, shadowRadius: 13, shadowOffset: { width: 0, height: 4 }, elevation: 2 },
  budgetTop: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' }, budgetValue: { color: C.text, fontSize: 25, fontWeight: '900', textAlign: 'right', marginTop: 5 },
  budgetIcon: { width: 40, height: 40, borderRadius: 14, backgroundColor: '#25452F', alignItems: 'center', justifyContent: 'center' }, budgetIconText: { color: C.lime },
  budgetControls: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 18 }, budgetAdjust: { width: 44, height: 44, borderRadius: 14, backgroundColor: C.panel2, borderWidth: 1, borderColor: '#315343', alignItems: 'center', justifyContent: 'center' },
  adjustText: { color: C.text, fontSize: 22, fontWeight: '600', lineHeight: 25 }, budgetSliderTouch: { flex: 1, height: 44, justifyContent: 'center', position: 'relative', paddingHorizontal: 9, touchAction: 'none' } as any, budgetTrack: { height: 9, borderRadius: 8, backgroundColor: '#355141', overflow: 'hidden' }, budgetFill: { height: 9, backgroundColor: C.lime, borderRadius: 8 }, budgetThumb: { position: 'absolute', top: 11, width: 22, height: 22, marginLeft: -11, borderRadius: 11, backgroundColor: C.lime, borderWidth: 3, borderColor: '#F4FFBF', elevation: 3 },
  budgetLimits: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 7 }, budgetLimitText: { color: '#89A393', fontSize: 9 },
  optimizeButton: { minHeight: 52, borderRadius: 16, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 9, marginTop: 13 },
  optimizeGlyph: { color: C.bg, fontSize: 17 }, optimizeText: { color: C.bg, fontSize: 13, fontWeight: '900' },
  squadPlaceholder: { borderRadius: 20, borderWidth: 1, borderStyle: 'dashed', borderColor: '#365846', alignItems: 'center', padding: 25, marginTop: 23 },
  placeholderIcon: { color: '#769682', fontSize: 29 }, placeholderTitle: { color: C.text, fontSize: 14, fontWeight: '800', marginTop: 9 }, placeholderBody: { color: C.muted, fontSize: 11, lineHeight: 18, textAlign: 'center', marginTop: 7 },
  tabBar: { minHeight: 67, backgroundColor: '#FFFFFF', borderTopWidth: 1, borderTopColor: '#E3E2DB', flexDirection: 'row-reverse', paddingHorizontal: 18, paddingBottom: 4 },
  tabButton: { flex: 1, alignItems: 'center', justifyContent: 'center', position: 'relative', gap: 2 }, tabIcon: { color: '#92978F', fontSize: 20, height: 24 }, tabIconActive: { color: '#657B57' }, tabLabel: { color: '#898E86', fontSize: 9, fontWeight: '600' }, tabLabelActive: { color: C.text },
  tabIndicator: { position: 'absolute', top: 0, height: 2, width: 20, borderRadius: 2, backgroundColor: C.lime },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 }, loadingText: { color: C.muted, fontSize: 12 },
  errorCard: { margin: 18, marginBottom: 0, padding: 15, backgroundColor: '#34201F', borderColor: '#724039', borderWidth: 1, borderRadius: 16 },
  errorTitle: { color: '#FFC0B6', fontWeight: '800', textAlign: 'right', fontSize: 13 }, errorBody: { color: C.text, textAlign: 'right', fontSize: 11, marginTop: 6 }, errorHint: { color: '#D5A49D', textAlign: 'right', fontSize: 10, lineHeight: 16, marginTop: 6 },
  retryButton: { alignSelf: 'flex-end', marginTop: 11, borderRadius: 10, backgroundColor: '#63372F', paddingVertical: 7, paddingHorizontal: 12 }, retryText: { color: C.text, fontSize: 10, fontWeight: '700' },
  emptyText: { color: C.muted, fontSize: 11, textAlign: 'right', paddingVertical: 18 },
});
