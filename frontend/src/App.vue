<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { BarChart3, Bot, Boxes, FileText, Megaphone, PackageSearch, RefreshCw, Settings, Sparkles } from 'lucide-vue-next'
import { api } from './api'

type Project = {
  id: number
  slug: string
  name: string
  telegram_channel_url?: string | null
  telegram_channel_id?: string | null
  niche: string
  description?: string | null
  tagline?: string | null
  accent_color: string
  accent_secondary: string
  logo_text: string
  category_focus_json?: string | null
  is_active: boolean
}

type Product = {
  id: number
  project_id?: number | null
  title: string
  brand?: string | null
  category: string
  price: number
  market_price?: number | null
  discount_percent?: number | null
  rating?: number | null
  reviews_count?: number | null
  stock_count?: number | null
  score: number
  source: string
  is_excluded: boolean
  is_published: boolean
  url?: string | null
}

type Draft = {
  id: number
  project_id?: number | null
  product_id?: number | null
  title: string
  text: string
  style: string
  status: string
  image_path?: string | null
  scheduled_for?: string | null
  created_at: string
  updated_at: string
}

type Published = {
  id: number
  project_id?: number | null
  published_at: string
  is_verified: boolean
}

type SyncRow = {
  project_id?: number | null
  source: string
  state: string
  total_items: number
  last_synced_at?: string | null
  last_error?: string | null
}

type LogRow = {
  id: number
  project_id?: number | null
  kind?: string
  provider?: string
  status?: string
  created_at: string
  result?: string | null
  error?: string | null
}

type SettingRow = { key: string; value: string }
type ReferralRow = {
  id: number
  project_id?: number | null
  source: string
  name: string
  template_url: string
  is_active: boolean
}

type AdPackage = {
  id: number
  code: string
  name: string
  description?: string | null
  amount: number
  duration_hours: number
  delete_after_hours: number
  is_active: boolean
  sort_order: number
}

type AdRequest = {
  id: number
  user_id: number
  chat_id: string
  username?: string | null
  full_name?: string | null
  text: string
  media_type: string
  media_file_id?: string | null
  media_local_path?: string | null
  status: string
  package_id?: number | null
  package_name?: string | null
  amount?: number | null
  payment_provider?: string | null
  payment_url?: string | null
  payment_links_json?: string | null
  admin_note?: string | null
  published_link?: string | null
  delete_at?: string | null
  paid_at?: string | null
  in_work_at?: string | null
  published_at?: string | null
  created_at: string
  updated_at: string
}

const projects = ref<Project[]>([])
const analytics = ref<any>(null)
const products = ref<Product[]>([])
const drafts = ref<Draft[]>([])
const published = ref<Published[]>([])
const syncStatus = ref<SyncRow[]>([])
const generationLogs = ref<LogRow[]>([])
const publishLogs = ref<LogRow[]>([])
const settings = ref<SettingRow[]>([])
const referrals = ref<ReferralRow[]>([])
const adPackages = ref<AdPackage[]>([])
const adRequests = ref<AdRequest[]>([])
const activeTab = ref<'dashboard' | 'products' | 'drafts' | 'ads' | 'logs' | 'settings'>('dashboard')
const notice = ref('')
const selectedStyle = ref('short')
const search = ref('')
const loadingAction = ref(false)
const selectedProductId = ref<number | null>(null)
const selectedDraftId = ref<number | null>(null)
const selectedAdRequestId = ref<number | null>(null)
const adRequestMediaUrl = api.adRequestMediaUrl
const adEditor = reactive({
  package_id: 0,
  provider: 'both',
  admin_note: '',
  published_link: '',
})
const settingsTestResult = ref('')
const settingsEditor = reactive({
  telegram_bot_token: '',
  telegram_bot_username: '',
  telegram_admin_id: '',
  yookassa_shop_id: '',
  yookassa_secret_key: '',
  yookassa_return_url: 'http://localhost:5173',
  cryptobot_api_token: '',
  cryptobot_asset: 'USDT',
  text_engine: 'openrouter',
  openrouter_api_key: '',
  openrouter_base_url: 'https://openrouter.ai/api/v1',
  openrouter_text_model: 'openrouter/cypher-alpha:free',
  openrouter_text_timeout_seconds: 180,
  openrouter_text_max_tokens: 900,
  openrouter_site_url: 'https://ai.sebog1.ru',
  openrouter_site_name: 'Aromat Day',
  image_engine: 'codex_sale',
  codex_sale_api_key: '',
  codex_sale_base_url: 'https://codex.sale/v1',
  codex_sale_image_model: 'gpt-image-2',
  codex_sale_image_size: '1024x1024',
  codex_sale_timeout_seconds: 300,
  image_generation_mode: 'image_to_image',
  ozon_feed_url: '',
  wildberries_feed_url: '',
  yandex_market_feed_url: '',
  marketplace_demo_mode: 'false',
  auto_posting_enabled: 'false',
  import_interval_minutes: 30,
  publish_interval_minutes: 5,
  telethon_api_id: 0,
  telethon_api_hash: '',
  telethon_session_name: 'tehno_halava_verifier',
})
const channelEditors = reactive<Record<number, {
  telegram_channel_url: string
  telegram_channel_id: string
  category_focus_json: string
  is_active: boolean
}>>({})

const productEditor = reactive({
  title: '',
  brand: '',
  category: '',
  price: 0,
  market_price: 0,
  discount_percent: 0,
  rating: 0,
  reviews_count: 0,
  stock_count: 0,
  url: '',
})

const draftEditor = reactive({
  title: '',
  text: '',
  style: 'short',
  image_path: '',
  status: 'review',
})

const filteredProducts = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return products.value
  return products.value.filter((product) => {
    const haystack = [product.title, product.brand, product.category, product.source, projectName(product.project_id)].join(' ').toLowerCase()
    return haystack.includes(q)
  })
})

const hasFilteredProducts = computed(() => filteredProducts.value.length > 0)

const pendingDrafts = computed(() => drafts.value.filter((item) => item.status === 'review').slice(0, 12))
const pendingAdRequests = computed(() => adRequests.value.filter((item) => ['draft', 'submitted', 'awaiting_payment', 'in_work'].includes(item.status)).slice(0, 12))
const selectedAdRequest = computed(() => adRequests.value.find((item) => item.id === selectedAdRequestId.value) || null)

const cards = computed(() => [
  { label: 'Товары', value: analytics.value?.products_total ?? 0 },
  { label: 'На согласовании', value: analytics.value?.drafts_pending ?? 0 },
  { label: 'Публикации', value: analytics.value?.published_total ?? 0 },
  { label: 'Проекты', value: projects.value.length },
])

const parserState = computed(() => {
  const ozon = settingMap('ozon_feed_url')
  const wb = settingMap('wildberries_feed_url')
  const ym = settingMap('yandex_market_feed_url')
  const demo = settingMap('marketplace_demo_mode') === 'true'
  return {
    ozon,
    wb,
    ym,
    demo,
    configured: Boolean(ozon || wb || ym),
  }
})

function projectName(projectId?: number | null) {
  if (!projectId) return 'Без проекта'
  return projects.value.find((item) => item.id === projectId)?.name || `Проект #${projectId}`
}

function fillProductEditor(product: Product) {
  selectedProductId.value = product.id
  productEditor.title = product.title ?? ''
  productEditor.brand = product.brand ?? ''
  productEditor.category = product.category ?? 'general'
  productEditor.price = product.price ?? 0
  productEditor.market_price = product.market_price ?? 0
  productEditor.discount_percent = product.discount_percent ?? 0
  productEditor.rating = product.rating ?? 0
  productEditor.reviews_count = product.reviews_count ?? 0
  productEditor.stock_count = product.stock_count ?? 0
  productEditor.url = product.url ?? ''
}

function fillDraftEditor(draft: Draft) {
  selectedDraftId.value = draft.id
  draftEditor.title = draft.title ?? ''
  draftEditor.text = draft.text ?? ''
  draftEditor.style = draft.style ?? 'review'
  draftEditor.image_path = draft.image_path ?? ''
  draftEditor.status = draft.status ?? 'review'
}

function fillAdEditor(request: AdRequest) {
  selectedAdRequestId.value = request.id
  adEditor.package_id = request.package_id || adPackages.value[0]?.id || 0
  adEditor.provider = request.payment_provider || 'both'
  adEditor.admin_note = request.admin_note || ''
  adEditor.published_link = request.published_link || ''
}

function hydrateSettingsEditors() {
  const map = Object.fromEntries(settings.value.map((item) => [item.key, item.value]))
  settingsEditor.telegram_bot_token = map.telegram_bot_token || settingsEditor.telegram_bot_token
  settingsEditor.telegram_bot_username = map.telegram_bot_username || ''
  settingsEditor.telegram_admin_id = map.telegram_admin_id || ''
  settingsEditor.yookassa_shop_id = map.yookassa_shop_id || ''
  settingsEditor.yookassa_secret_key = map.yookassa_secret_key || settingsEditor.yookassa_secret_key
  settingsEditor.yookassa_return_url = map.yookassa_return_url || settingsEditor.yookassa_return_url
  settingsEditor.cryptobot_api_token = map.cryptobot_api_token || settingsEditor.cryptobot_api_token
  settingsEditor.cryptobot_asset = map.cryptobot_asset || settingsEditor.cryptobot_asset
  settingsEditor.text_engine = map.text_engine || settingsEditor.text_engine
  settingsEditor.openrouter_api_key = map.openrouter_api_key || settingsEditor.openrouter_api_key
  settingsEditor.openrouter_base_url = map.openrouter_base_url || settingsEditor.openrouter_base_url
  settingsEditor.openrouter_text_model = map.openrouter_text_model || settingsEditor.openrouter_text_model
  settingsEditor.openrouter_text_timeout_seconds = Number(map.openrouter_text_timeout_seconds || settingsEditor.openrouter_text_timeout_seconds)
  settingsEditor.openrouter_text_max_tokens = Number(map.openrouter_text_max_tokens || settingsEditor.openrouter_text_max_tokens)
  settingsEditor.openrouter_site_url = map.openrouter_site_url || settingsEditor.openrouter_site_url
  settingsEditor.openrouter_site_name = map.openrouter_site_name || settingsEditor.openrouter_site_name
  settingsEditor.image_engine = map.image_engine || settingsEditor.image_engine
  settingsEditor.codex_sale_api_key = map.codex_sale_api_key || settingsEditor.codex_sale_api_key
  settingsEditor.codex_sale_base_url = map.codex_sale_base_url || settingsEditor.codex_sale_base_url
  settingsEditor.codex_sale_image_model = map.codex_sale_image_model || settingsEditor.codex_sale_image_model
  settingsEditor.codex_sale_image_size = map.codex_sale_image_size || settingsEditor.codex_sale_image_size
  settingsEditor.codex_sale_timeout_seconds = Number(map.codex_sale_timeout_seconds || settingsEditor.codex_sale_timeout_seconds)
  settingsEditor.image_generation_mode = map.image_generation_mode || settingsEditor.image_generation_mode
  settingsEditor.ozon_feed_url = map.ozon_feed_url || ''
  settingsEditor.wildberries_feed_url = map.wildberries_feed_url || ''
  settingsEditor.yandex_market_feed_url = map.yandex_market_feed_url || ''
  settingsEditor.marketplace_demo_mode = map.marketplace_demo_mode || settingsEditor.marketplace_demo_mode
  settingsEditor.auto_posting_enabled = map.auto_posting_enabled || settingsEditor.auto_posting_enabled
  settingsEditor.import_interval_minutes = Number(map.import_interval_minutes || settingsEditor.import_interval_minutes)
  settingsEditor.publish_interval_minutes = Number(map.publish_interval_minutes || settingsEditor.publish_interval_minutes)
  settingsEditor.telethon_api_id = Number(map.telethon_api_id || settingsEditor.telethon_api_id)
  settingsEditor.telethon_api_hash = map.telethon_api_hash || settingsEditor.telethon_api_hash
  settingsEditor.telethon_session_name = map.telethon_session_name || settingsEditor.telethon_session_name
}

function hydrateChannelEditors() {
  for (const project of projects.value) {
    channelEditors[project.id] = {
      telegram_channel_url: project.telegram_channel_url || '',
      telegram_channel_id: project.telegram_channel_id || '',
      category_focus_json: project.category_focus_json || '',
      is_active: project.is_active,
    }
  }
}

async function reloadAll() {
  const [projectRows, a, p, d, s, r, pub, sync, glogs, plogs, adPkg, adReq] = await Promise.all([
    api.projects(),
    api.analytics(),
    api.products(),
    api.drafts(),
    api.settings(),
    api.referrals(),
    api.published(),
    api.syncStatus(),
    api.generationLogs(),
    api.publishLogs(),
    api.adPackages(),
    api.adRequests(),
  ])
  projects.value = projectRows
  analytics.value = a
  products.value = p
  drafts.value = d
  settings.value = s
  referrals.value = r
  published.value = pub
  syncStatus.value = sync
  generationLogs.value = glogs
  publishLogs.value = plogs
  adPackages.value = adPkg
  adRequests.value = adReq
  hydrateSettingsEditors()
  hydrateChannelEditors()
  if (!adEditor.package_id && adPkg.length) {
    adEditor.package_id = adPkg[0].id
  }
  if (selectedProductId.value) {
    const current = p.find((item: Product) => item.id === selectedProductId.value)
    if (current) fillProductEditor(current)
  }
  if (selectedDraftId.value) {
    const current = d.find((item: Draft) => item.id === selectedDraftId.value)
    if (current) fillDraftEditor(current)
  }
  if (selectedAdRequestId.value) {
    const current = adReq.find((item: AdRequest) => item.id === selectedAdRequestId.value)
    if (current) fillAdEditor(current)
  }
}

async function createQueue() {
  loadingAction.value = true
  notice.value = 'Собираю товары и готовлю очередь...'
  try {
    await api.importAndDraft(selectedStyle.value)
    await reloadAll()
    notice.value = 'Очередь обновлена'
  } finally {
    loadingAction.value = false
  }
}

async function createDraft(productId: number) {
  loadingAction.value = true
  try {
    const draft = await api.createDraft(productId, selectedStyle.value)
    await reloadAll()
    selectedDraftId.value = draft.id
    notice.value = 'Черновик отправлен на согласование'
  } finally {
    loadingAction.value = false
  }
}

async function decideDraft(draftId: number, action: 'approve' | 'reject' | 'redo' | 'next') {
  loadingAction.value = true
  try {
    await api.decideDraft(draftId, action)
    await reloadAll()
    notice.value = action === 'approve' ? 'Пост одобрен' : action === 'reject' ? 'Пост отменён' : 'Готовлю другой товар'
  } finally {
    loadingAction.value = false
  }
}

async function refreshDraft(draftId: number) {
  loadingAction.value = true
  try {
    await api.regenerateDraft(draftId)
    await reloadAll()
    notice.value = 'Черновик переделан'
  } finally {
    loadingAction.value = false
  }
}

async function saveProduct() {
  if (!selectedProductId.value) return
  loadingAction.value = true
  try {
    await api.updateProduct(selectedProductId.value, {
      title: productEditor.title,
      brand: productEditor.brand,
      category: productEditor.category,
      price: Number(productEditor.price),
      market_price: Number(productEditor.market_price),
      discount_percent: Number(productEditor.discount_percent),
      rating: Number(productEditor.rating),
      reviews_count: Number(productEditor.reviews_count),
      stock_count: Number(productEditor.stock_count),
      url: productEditor.url,
    })
    await reloadAll()
    notice.value = 'Товар сохранён'
  } finally {
    loadingAction.value = false
  }
}

async function saveDraft() {
  if (!selectedDraftId.value) return
  loadingAction.value = true
  try {
    await api.updateDraft(selectedDraftId.value, {
      title: draftEditor.title,
      text: draftEditor.text,
      style: draftEditor.style,
      image_path: draftEditor.image_path,
      status: draftEditor.status,
    })
    await reloadAll()
    notice.value = 'Черновик сохранён'
  } finally {
    loadingAction.value = false
  }
}

async function saveAdRequest() {
  if (!selectedAdRequestId.value) return
  loadingAction.value = true
  try {
    await api.updateAdRequest(selectedAdRequestId.value, {
      package_id: adEditor.package_id || null,
      payment_provider: adEditor.provider,
      admin_note: adEditor.admin_note,
      published_link: adEditor.published_link || null,
    })
    await reloadAll()
    notice.value = 'Рекламная заявка обновлена'
  } finally {
    loadingAction.value = false
  }
}

async function sendInvoice() {
  if (!selectedAdRequestId.value || !adEditor.package_id) return
  loadingAction.value = true
  try {
    await api.createAdInvoice(selectedAdRequestId.value, {
      package_id: adEditor.package_id,
      provider: adEditor.provider,
      note: adEditor.admin_note,
    })
    await reloadAll()
    notice.value = 'Счет отправлен'
  } finally {
    loadingAction.value = false
  }
}

async function markAdPaid() {
  if (!selectedAdRequestId.value) return
  loadingAction.value = true
  try {
    await api.markAdPaid(selectedAdRequestId.value)
    await reloadAll()
    notice.value = 'Оплата отмечена'
  } finally {
    loadingAction.value = false
  }
}

async function publishAdRequest() {
  if (!selectedAdRequestId.value) return
  loadingAction.value = true
  try {
    await api.publishAd(selectedAdRequestId.value, {
      published_link: adEditor.published_link || null,
      publish_to_channels: !adEditor.published_link,
    })
    await reloadAll()
    notice.value = 'Реклама опубликована'
  } finally {
    loadingAction.value = false
  }
}

async function saveOperationalSettings() {
  loadingAction.value = true
  settingsTestResult.value = ''
  try {
    await api.updateSettings({
      telegram_bot_token: settingsEditor.telegram_bot_token,
      telegram_bot_username: settingsEditor.telegram_bot_username,
      telegram_admin_id: settingsEditor.telegram_admin_id,
      yookassa_shop_id: settingsEditor.yookassa_shop_id,
      yookassa_secret_key: settingsEditor.yookassa_secret_key,
      yookassa_return_url: settingsEditor.yookassa_return_url,
      cryptobot_api_token: settingsEditor.cryptobot_api_token,
      cryptobot_asset: settingsEditor.cryptobot_asset,
      text_engine: settingsEditor.text_engine,
      openrouter_api_key: settingsEditor.openrouter_api_key,
      openrouter_base_url: settingsEditor.openrouter_base_url,
      openrouter_text_model: settingsEditor.openrouter_text_model,
      openrouter_text_timeout_seconds: String(settingsEditor.openrouter_text_timeout_seconds),
      openrouter_text_max_tokens: String(settingsEditor.openrouter_text_max_tokens),
      openrouter_site_url: settingsEditor.openrouter_site_url,
      openrouter_site_name: settingsEditor.openrouter_site_name,
      image_engine: settingsEditor.image_engine,
      codex_sale_api_key: settingsEditor.codex_sale_api_key,
      codex_sale_base_url: settingsEditor.codex_sale_base_url,
      codex_sale_image_model: settingsEditor.codex_sale_image_model,
      codex_sale_image_size: settingsEditor.codex_sale_image_size,
      codex_sale_timeout_seconds: String(settingsEditor.codex_sale_timeout_seconds),
      image_generation_mode: settingsEditor.image_generation_mode,
      ozon_feed_url: settingsEditor.ozon_feed_url,
      wildberries_feed_url: settingsEditor.wildberries_feed_url,
      yandex_market_feed_url: settingsEditor.yandex_market_feed_url,
      marketplace_demo_mode: settingsEditor.marketplace_demo_mode,
      auto_posting_enabled: settingsEditor.auto_posting_enabled,
      import_interval_minutes: String(settingsEditor.import_interval_minutes),
      publish_interval_minutes: String(settingsEditor.publish_interval_minutes),
      telethon_api_id: String(settingsEditor.telethon_api_id),
      telethon_api_hash: settingsEditor.telethon_api_hash,
      telethon_session_name: settingsEditor.telethon_session_name,
    })
    await reloadAll()
    notice.value = 'Настройки бота и касс сохранены'
  } finally {
    loadingAction.value = false
  }
}

async function saveChannels() {
  loadingAction.value = true
  settingsTestResult.value = ''
  try {
    for (const project of projects.value) {
      const editor = channelEditors[project.id]
      if (!editor) continue
      await api.updateProject(project.id, {
        telegram_channel_url: editor.telegram_channel_url,
        telegram_channel_id: editor.telegram_channel_id,
        category_focus_json: editor.category_focus_json,
        is_active: editor.is_active,
      })
    }
    await reloadAll()
    notice.value = 'Каналы сохранены'
  } finally {
    loadingAction.value = false
  }
}

async function runSettingsTest(kind: 'token' | 'admin' | 'channels' | 'payments') {
  loadingAction.value = true
  settingsTestResult.value = ''
  try {
    const result = kind === 'token'
      ? await api.testTelegramToken()
      : kind === 'admin'
        ? await api.testTelegramAdmin()
        : kind === 'channels'
          ? await api.testTelegramChannels()
          : await api.testPaymentSettings()
    settingsTestResult.value = JSON.stringify(result, null, 2)
    notice.value = 'Тест выполнен'
    await reloadAll()
  } catch (error: any) {
    settingsTestResult.value = error?.message || String(error)
    notice.value = 'Тест завершился ошибкой'
  } finally {
    loadingAction.value = false
  }
}

function settingMap(key: string): string {
  return settings.value.find((item) => item.key === key)?.value ?? ''
}

onMounted(reloadAll)
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">ТК</div>
        <div>
          <div class="brand-name">Единый кабинет</div>
          <div class="brand-sub">Автопоток, Telegram и веб-согласование</div>
        </div>
      </div>

      <nav class="nav">
        <button :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'"><BarChart3 />Дашборд</button>
        <button :class="{ active: activeTab === 'products' }" @click="activeTab = 'products'"><Boxes />Товары</button>
        <button :class="{ active: activeTab === 'drafts' }" @click="activeTab = 'drafts'"><FileText />Черновики</button>
        <button :class="{ active: activeTab === 'ads' }" @click="activeTab = 'ads'"><Megaphone />Реклама</button>
        <button :class="{ active: activeTab === 'logs' }" @click="activeTab = 'logs'"><Bot />Логи</button>
        <button :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'"><Settings />Настройки</button>
      </nav>

      <div class="side-card">
        <label>Стиль генерации</label>
        <select v-model="selectedStyle">
          <option value="short">Короткий</option>
          <option value="selling">Продающий</option>
          <option value="expert">Экспертный</option>
          <option value="premium">Премиальный</option>
          <option value="bundle">Подборка</option>
          <option value="comparison">Сравнительный</option>
        </select>
        <button class="primary" :disabled="loadingAction" @click="createQueue"><Sparkles />Обновить очередь</button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <h1>Единая админка для всех проектов</h1>
          <p>Поток товаров идёт автономно, а решения по постам приходят в Telegram и в веб.</p>
        </div>
        <div class="actions">
          <button class="ghost" :disabled="loadingAction" @click="reloadAll"><RefreshCw />Обновить</button>
        </div>
      </header>

      <section v-if="notice" class="notice">{{ notice }}</section>

      <section class="metrics">
        <article v-for="card in cards" :key="card.label" class="metric">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
        </article>
      </section>

      <section v-if="activeTab === 'dashboard'" class="grid-two">
        <div class="panel">
          <div class="panel-head">
            <h2>Очередь на согласование</h2>
            <span>{{ pendingDrafts.length }} карточек</span>
          </div>
          <div class="draft-grid">
            <article v-for="draft in pendingDrafts" :key="draft.id" class="draft-card">
              <div class="draft-meta">
                <strong>{{ draft.title }}</strong>
                <span>{{ projectName(draft.project_id) }} · {{ draft.style }} · {{ draft.status }}</span>
              </div>
              <p>{{ draft.text }}</p>
              <div class="draft-actions">
                <button class="primary" @click="decideDraft(draft.id, 'approve')">Одобрить</button>
                <button class="ghost" @click="decideDraft(draft.id, 'reject')">Отменить</button>
                <button class="ghost" @click="decideDraft(draft.id, 'redo')">Переделать</button>
                <button class="ghost" @click="decideDraft(draft.id, 'next')">Другой товар</button>
              </div>
            </article>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Проекты</h2>
            <span>{{ projects.length }} шт.</span>
          </div>
          <div class="list">
            <div v-for="project in projects" :key="project.id" class="row">
              <div class="row-main">
                <strong>{{ project.name }}</strong>
                <span>{{ project.niche }}</span>
              </div>
              <div class="row-side">
                <span>{{ project.telegram_channel_url }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'products'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Товары</h2>
            <span>{{ filteredProducts.length }} позиций</span>
          </div>
          <div class="toolbar">
            <input v-model="search" placeholder="Поиск по товарам, брендам, проектам" />
          </div>
          <div v-if="hasFilteredProducts" class="table">
            <div class="table-row table-head">
              <span>Товар</span>
              <span>Проект</span>
              <span>Цена</span>
              <span>Статус</span>
              <span></span>
            </div>
            <div v-for="product in filteredProducts" :key="product.id" class="table-row">
              <span class="cell-title">
                <strong>{{ product.title }}</strong>
                <small>{{ product.brand || 'Без бренда' }} · {{ product.category }}</small>
              </span>
              <span>{{ projectName(product.project_id) }}</span>
              <span>{{ product.price.toLocaleString('ru-RU') }} ₽</span>
              <span>
                <span class="status-pill" :class="product.is_published ? 'status-pill-success' : product.is_excluded ? 'status-pill-danger' : 'status-pill-neutral'">
                  {{ product.is_published ? 'Опубликован' : product.is_excluded ? 'Исключён' : 'Активен' }}
                </span>
              </span>
              <span class="row-actions">
                <button @click="fillProductEditor(product)">Открыть</button>
                <button class="primary" @click="createDraft(product.id)">Пост</button>
              </span>
            </div>
          </div>
          <div v-else class="empty-state">
            <PackageSearch />
            <strong>Пока нет товаров в очереди</strong>
            <p>Нажми «Обновить очередь» слева, чтобы подтянуть свежие позиции и собрать рабочую витрину.</p>
            <div class="toggle-row">
              <button class="primary" @click="createQueue">Собрать очередь</button>
              <button class="ghost" @click="reloadAll">Обновить список</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Карточка товара</h2>
            <span>{{ selectedProductId ? `ID ${selectedProductId}` : 'Выберите товар' }}</span>
          </div>
          <div class="product-summary">
            <div>
              <span>Текущая позиция</span>
              <strong>{{ productEditor.title || 'ничего не выбрано' }}</strong>
            </div>
            <div>
              <span>Цена</span>
              <strong>{{ Number(productEditor.price || 0).toLocaleString('ru-RU') }} ₽</strong>
            </div>
          </div>
          <div class="form-grid">
            <label class="wide-field"><span>Название</span><input v-model="productEditor.title" /></label>
            <label><span>Бренд</span><input v-model="productEditor.brand" /></label>
            <label><span>Категория</span><input v-model="productEditor.category" /></label>
            <label><span>Цена</span><input v-model.number="productEditor.price" type="number" /></label>
            <label><span>Рынок</span><input v-model.number="productEditor.market_price" type="number" /></label>
            <label><span>Скидка</span><input v-model.number="productEditor.discount_percent" type="number" /></label>
            <label><span>Рейтинг</span><input v-model.number="productEditor.rating" type="number" step="0.1" /></label>
            <label><span>Отзывы</span><input v-model.number="productEditor.reviews_count" type="number" /></label>
            <label><span>Остаток</span><input v-model.number="productEditor.stock_count" type="number" /></label>
            <label class="wide-field"><span>Ссылка</span><input v-model="productEditor.url" /></label>
          </div>
          <div class="toggle-row compact-actions">
            <button class="primary" @click="saveProduct">Сохранить</button>
            <button class="ghost" @click="selectedProductId && createDraft(selectedProductId)">Сделать пост</button>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'drafts'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Черновики</h2>
            <span>{{ drafts.length }} шт.</span>
          </div>
          <div class="draft-grid">
            <article v-for="draft in drafts" :key="draft.id" class="draft-card" @click="fillDraftEditor(draft)">
              <div class="draft-meta">
                <strong>{{ draft.title }}</strong>
                <span>{{ projectName(draft.project_id) }} · {{ draft.status }}</span>
              </div>
              <p>{{ draft.text }}</p>
              <div class="draft-actions">
                <button class="primary" @click.stop="decideDraft(draft.id, 'approve')">Одобрить</button>
                <button class="ghost" @click.stop="decideDraft(draft.id, 'reject')">Отменить</button>
                <button class="ghost" @click.stop="decideDraft(draft.id, 'redo')">Переделать</button>
                <button class="ghost" @click.stop="refreshDraft(draft.id)">Перегенерировать</button>
              </div>
            </article>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Редактор черновика</h2>
            <span>{{ selectedDraftId ? `ID ${selectedDraftId}` : 'Выберите черновик' }}</span>
          </div>
          <div class="form-grid">
            <label><span>Заголовок</span><input v-model="draftEditor.title" /></label>
            <label><span>Стиль</span><input v-model="draftEditor.style" /></label>
            <label><span>Статус</span><input v-model="draftEditor.status" /></label>
            <label><span>Изображение</span><input v-model="draftEditor.image_path" /></label>
          </div>
          <label class="block-field">
            <span>Текст поста</span>
            <textarea v-model="draftEditor.text" rows="12" />
          </label>
          <div class="toggle-row">
            <button class="primary" @click="saveDraft">Сохранить</button>
            <button class="ghost" @click="selectedDraftId && decideDraft(selectedDraftId, 'approve')">Одобрить</button>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'ads'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Рекламные заявки</h2>
            <span>{{ pendingAdRequests.length }} активных</span>
          </div>
          <div class="draft-grid">
            <article v-for="item in pendingAdRequests" :key="item.id" class="draft-card" @click="fillAdEditor(item)">
              <div class="draft-meta">
                <strong>{{ item.full_name || item.username || item.user_id }}</strong>
                <span>{{ item.status }} · {{ item.package_name || 'пакет не выбран' }}</span>
              </div>
              <p>{{ item.text }}</p>
              <div class="draft-actions">
                <button class="primary" @click.stop="fillAdEditor(item)">Открыть</button>
                <button class="ghost" @click.stop="selectedAdRequestId = item.id">Выбрать</button>
              </div>
            </article>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Карточка рекламы</h2>
            <span>{{ selectedAdRequestId ? `ID ${selectedAdRequestId}` : 'Выберите заявку' }}</span>
          </div>
          <div class="form-grid">
            <label>
              <span>Пакет</span>
              <select v-model.number="adEditor.package_id">
                <option v-for="pack in adPackages" :key="pack.id" :value="pack.id">{{ pack.name }} · {{ pack.amount.toLocaleString('ru-RU') }} ₽</option>
              </select>
            </label>
            <label>
              <span>Платёж</span>
              <select v-model="adEditor.provider">
                <option value="both">YooKassa + CryptoBot</option>
                <option value="yookassa">YooKassa</option>
                <option value="cryptobot">CryptoBot</option>
              </select>
            </label>
            <label><span>Публикационный link</span><input v-model="adEditor.published_link" placeholder="https://t.me/..." /></label>
          </div>
          <label class="block-field">
            <span>Комментарий</span>
            <textarea v-model="adEditor.admin_note" rows="4" />
          </label>
          <div v-if="selectedAdRequestId && selectedAdRequest?.media_local_path" class="block-field">
            <span>Медиа</span>
            <img :src="adRequestMediaUrl(selectedAdRequestId)" alt="ad media" class="ad-preview" />
          </div>
          <div class="toggle-row">
            <button class="primary" @click="saveAdRequest">Сохранить</button>
            <button class="ghost" @click="sendInvoice">Выставить счёт</button>
            <button class="ghost" @click="markAdPaid">Оплата получена</button>
            <button class="ghost" @click="publishAdRequest">Опубликовать / отправить ссылку</button>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'logs'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Логи генерации</h2>
            <span>{{ generationLogs.length }} записей</span>
          </div>
          <div class="log-list">
            <article v-for="item in generationLogs" :key="item.id" class="log-row">
              <strong>{{ projectName(item.project_id) }} · {{ item.kind }} · {{ item.provider }}</strong>
              <span>{{ item.created_at }}</span>
              <p>{{ item.error || item.result }}</p>
            </article>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Логи публикаций</h2>
            <span>{{ publishLogs.length }} записей</span>
          </div>
          <div class="log-list">
            <article v-for="item in publishLogs" :key="item.id" class="log-row">
              <strong>{{ projectName(item.project_id) }} · {{ item.status }}</strong>
              <span>{{ item.created_at }}</span>
              <p>{{ item.error || item.result || item.status }}</p>
            </article>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'settings'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Бот и кассы</h2>
            <span>Хранится в админ-панели</span>
          </div>
          <div class="form-grid">
            <label><span>Telegram bot token</span><input v-model="settingsEditor.telegram_bot_token" placeholder="123456:ABC..." /></label>
            <label><span>Bot username</span><input v-model="settingsEditor.telegram_bot_username" placeholder="my_bot" /></label>
            <label><span>Admin Telegram ID</span><input v-model="settingsEditor.telegram_admin_id" placeholder="123456789" /></label>
            <label><span>YooKassa shop id</span><input v-model="settingsEditor.yookassa_shop_id" /></label>
            <label><span>YooKassa secret</span><input v-model="settingsEditor.yookassa_secret_key" type="password" /></label>
            <label><span>YooKassa return url</span><input v-model="settingsEditor.yookassa_return_url" /></label>
            <label><span>CryptoBot token</span><input v-model="settingsEditor.cryptobot_api_token" type="password" /></label>
            <label><span>CryptoBot asset</span><input v-model="settingsEditor.cryptobot_asset" /></label>
            <label><span>Text engine</span><input v-model="settingsEditor.text_engine" /></label>
            <label><span>OpenRouter key</span><input v-model="settingsEditor.openrouter_api_key" type="password" placeholder="sk-or-v1..." /></label>
            <label><span>OpenRouter base URL</span><input v-model="settingsEditor.openrouter_base_url" /></label>
            <label><span>OpenRouter model</span><input v-model="settingsEditor.openrouter_text_model" /></label>
            <label><span>OpenRouter timeout</span><input v-model.number="settingsEditor.openrouter_text_timeout_seconds" type="number" /></label>
            <label><span>OpenRouter max tokens</span><input v-model.number="settingsEditor.openrouter_text_max_tokens" type="number" /></label>
            <label><span>OpenRouter site URL</span><input v-model="settingsEditor.openrouter_site_url" /></label>
            <label><span>OpenRouter site name</span><input v-model="settingsEditor.openrouter_site_name" /></label>
            <label><span>Image engine</span><input v-model="settingsEditor.image_engine" /></label>
            <label><span>Codex Sale key</span><input v-model="settingsEditor.codex_sale_api_key" type="password" placeholder="sk-clb..." /></label>
            <label><span>Codex Sale base URL</span><input v-model="settingsEditor.codex_sale_base_url" /></label>
            <label><span>Image model</span><input v-model="settingsEditor.codex_sale_image_model" /></label>
            <label><span>Image size</span><input v-model="settingsEditor.codex_sale_image_size" /></label>
            <label><span>Image timeout</span><input v-model.number="settingsEditor.codex_sale_timeout_seconds" type="number" /></label>
            <label><span>Image mode</span><input v-model="settingsEditor.image_generation_mode" /></label>
            <label><span>Ozon feed URL</span><input v-model="settingsEditor.ozon_feed_url" /></label>
            <label><span>Wildberries feed URL</span><input v-model="settingsEditor.wildberries_feed_url" /></label>
            <label><span>Yandex Market feed URL</span><input v-model="settingsEditor.yandex_market_feed_url" /></label>
            <label><span>Demo mode</span><input v-model="settingsEditor.marketplace_demo_mode" /></label>
            <label><span>Auto posting</span><input v-model="settingsEditor.auto_posting_enabled" /></label>
            <label><span>Import interval</span><input v-model.number="settingsEditor.import_interval_minutes" type="number" /></label>
            <label><span>Publish interval</span><input v-model.number="settingsEditor.publish_interval_minutes" type="number" /></label>
            <label><span>Telethon API ID</span><input v-model.number="settingsEditor.telethon_api_id" type="number" /></label>
            <label><span>Telethon API hash</span><input v-model="settingsEditor.telethon_api_hash" type="password" /></label>
            <label><span>Telethon session</span><input v-model="settingsEditor.telethon_session_name" /></label>
          </div>
          <div class="toggle-row">
            <button class="primary" :disabled="loadingAction" @click="saveOperationalSettings">Сохранить бота и кассы</button>
            <button class="ghost" :disabled="loadingAction" @click="runSettingsTest('token')">Тест токена бота</button>
            <button class="ghost" :disabled="loadingAction" @click="runSettingsTest('admin')">Тест админу</button>
            <button class="ghost" :disabled="loadingAction" @click="runSettingsTest('payments')">Тест касс</button>
          </div>
          <pre v-if="settingsTestResult" class="test-output">{{ settingsTestResult }}</pre>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Каналы проектов</h2>
            <span>{{ projects.length }} канала</span>
          </div>
          <div class="list">
            <div v-for="project in projects" :key="project.id" class="settings-card">
              <div class="settings-card-head">
                <strong>{{ project.name }}</strong>
                <label class="inline-check">
                  <input v-model="channelEditors[project.id].is_active" type="checkbox" />
                  <span>Активен</span>
                </label>
              </div>
              <label><span>Ссылка канала</span><input v-model="channelEditors[project.id].telegram_channel_url" placeholder="https://t.me/channel" /></label>
              <label><span>ID / @username канала</span><input v-model="channelEditors[project.id].telegram_channel_id" placeholder="@channel или -100..." /></label>
              <label class="block-field"><span>Категории проекта</span><textarea v-model="channelEditors[project.id].category_focus_json" rows="3" placeholder='["keyboards","monitors"] или keyboards, monitors'></textarea></label>
              <p class="help-text">Укажи категории через запятую или JSON-массив. Импорт оставит только товары из этих тем.</p>
            </div>
          </div>
          <div class="toggle-row">
            <button class="primary" :disabled="loadingAction" @click="saveChannels">Сохранить каналы</button>
            <button class="ghost" :disabled="loadingAction" @click="runSettingsTest('channels')">Тест бота во всех каналах</button>
          </div>
          <div class="parser-state" :class="{ 'parser-state-warn': !parserState.configured }">
            <div>
              <span>Состояние парсера</span>
              <strong>{{ parserState.configured ? 'Фиды подключены' : 'Фиды не заданы' }}</strong>
            </div>
            <div>
              <span>Demo mode</span>
              <strong>{{ parserState.demo ? 'включён' : 'выключен' }}</strong>
            </div>
            <p>
              {{ parserState.configured
                ? 'Импорт берёт только реальные фиды. Demo-карточки не подставляются.'
                : 'Если фиды Ozon / Wildberries / Yandex Market не заполнены, импорт не будет подсовывать фейковые товары.' }}
            </p>
          </div>
        </div>
      </section>

      <section v-if="false && activeTab === 'settings'" class="split-layout">
        <div class="panel">
          <div class="panel-head">
            <h2>Система</h2>
            <span>Автопоток и Telegram</span>
          </div>
          <div class="status-stack">
            <div class="status-item">
              <span>Тема</span>
              <strong>{{ settingMap('theme') }}</strong>
            </div>
            <div class="status-item">
              <span>Автопостинг</span>
              <strong>{{ settingMap('auto_posting_enabled') }}</strong>
            </div>
            <div class="status-item">
              <span>Админ Telegram ID</span>
              <strong>{{ settingMap('telegram_admin_id') || 'из .env' }}</strong>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h2>Рефералы</h2>
            <span>{{ referrals.length }} шаблонов</span>
          </div>
          <div class="list">
            <div v-for="item in referrals" :key="item.id" class="row">
              <div class="row-main">
                <strong>{{ item.name }}</strong>
                <span>{{ projectName(item.project_id) }} · {{ item.source }}</span>
              </div>
              <div class="row-side">
                <span>{{ item.template_url }}</span>
              </div>
            </div>
          </div>
          <div class="panel-head sub-head">
            <h2>Проекты</h2>
          </div>
          <div class="list">
            <div v-for="project in projects" :key="project.id" class="row">
              <div class="row-main">
                <strong>{{ project.name }}</strong>
                <span>{{ project.niche }}</span>
              </div>
              <div class="row-side">
                <span>{{ project.telegram_channel_url }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
