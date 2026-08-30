// Alpine.js-компонент главной (и единственной) страницы.
// Логика соответствует разделу 2 и 7 ТЗ. API_BASE берётся из config.js.

const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "";

// Панграммы по умолчанию для превью-текста (раздел 2, п.3 ТЗ: "если
// пользователь не ввёл — использовать дефолтный текст (панграмма на
// выбранном языке)"). Ключи — коды subset'ов Google Fonts.
const DEFAULT_PANGRAMS = {
  latin: "The quick brown fox jumps over the lazy dog",
  "latin-ext": "The quick brown fox jumps over the lazy dog",
  cyrillic: "Съешь же ещё этих мягких французских булок, да выпей чаю",
  "cyrillic-ext": "Съешь же ещё этих мягких французских булок, да выпей чаю",
  greek: "Γαζέες καὶ μυρτιὲς δὲν θὰ βρῶ πιὰ στὸ χρυσαφὶ ξέφωτο",
  vietnamese: "Chàng dũng sĩ đêm nay bắn giặc từ xa và bảo vệ quê hương",
  hebrew: "דג סקרן שט בים מאוכזב ולפתע מצא חברה",
  arabic: "نص حكيم له سر قاطع وذو شأن عظيم مكتوب على ثوب أخضر",
  devanagari: "ऋषियों को सताने वाले दुष्ट राक्षसों के राजा रावण का सर्वनाश करने वाले विष्णुवतार भगवान श्रीराम",
  thai: "เป็นมนุษย์สุดประเสริฐเลิศคุณค่า กว่าบรรดาฝูงสัตว์เดรัจฉาน",
  korean: "다람쥐 헌 쳇바퀴에 타고파",
  japanese: "いろはにほへと ちりぬるを わかよたれそ つねならむ",
  "chinese-simplified": "视端容寂，虚心宅意",
  "chinese-traditional": "視端容寂，虛心宅意",
  menu: "The quick brown fox jumps over the lazy dog",
};
const FALLBACK_PANGRAM = DEFAULT_PANGRAMS.latin;

function fontMatcher() {
  return {
    // --- справочники ---
    tags: [],
    languages: [],

    // --- состояние формы ---
    query: {
      text: "",
      preview_text: "",
      languages: ["latin"], // дефолт — English (раздел 2, п.4 ТЗ)
    },
    selectedTagIds: [],
    languageSearch: "",

    // --- состояние результатов ---
    fonts: [],
    searchId: null,
    hasMore: false,
    hasSearched: false,
    loading: false,
    loadingMore: false,
    errorMessage: "",

    // --- вспомогательное состояние ---
    totalFontsLabel: "free Google Fonts",
    _injectedFontFaces: new Set(),

    async init() {
      try {
        const [tagsRes, langsRes] = await Promise.all([
          fetch(`${API_BASE}/api/tags`),
          fetch(`${API_BASE}/api/languages`),
        ]);
        if (!tagsRes.ok || !langsRes.ok) throw new Error("init failed");
        const tagsData = await tagsRes.json();
        const langsData = await langsRes.json();
        this.tags = tagsData.tags;
        this.languages = langsData.languages;
      } catch (e) {
        this.errorMessage =
          "Could not load tags/languages. Check that the backend is running, then reload the page.";
      }
    },

    // ---------- Теги (раздел 2, excludes-логика раздела 4.1) ----------

    isTagDisabled(tagId) {
      if (this.selectedTagIds.includes(tagId)) return false;

      // дизейблим противоположный тег из excludes
      const tag = this.tags.find((t) => t.id === tagId);
      const excludedByPair =
        tag && tag.excludes.some((ex) => this.selectedTagIds.includes(ex));
      if (excludedByPair) return true;

      // дизейблим всё сверх лимита в 4 тега
      if (this.selectedTagIds.length >= 4) return true;

      return false;
    },

    toggleTag(tagId) {
      if (this.selectedTagIds.includes(tagId)) {
        this.selectedTagIds = this.selectedTagIds.filter((id) => id !== tagId);
        return;
      }
      if (this.isTagDisabled(tagId)) return;
      this.selectedTagIds = [...this.selectedTagIds, tagId];
    },

    // ---------- Языки (раздел 2, п.4: минимум один всегда выбран) ----------

    // Список для дропдауна: сначала уже выбранные языки (быстро видно и
    // снять их), затем остальные — и всё это дополнительно фильтруется
    // текстовым поиском ПО ПРЕФИКСУ: совпадение, если то, что напечатано,
    // является началом кода языка ИЛИ началом любого слова в названии
    // (например "rus" находит "Cyrillic (Russian, etc.)" по слову
    // "Russian", хотя само название начинается на "Cyrillic"). Порядок
    // внутри каждой группы не меняется (стабильная сортировка), чтобы
    // список не "прыгал" при наборе текста.
    get sortedFilteredLanguages() {
      const q = this.languageSearch.trim().toLowerCase();
      const filtered = q
        ? this.languages.filter((l) => {
            if (l.code.toLowerCase().startsWith(q)) return true;
            const words = l.label.toLowerCase().split(/[^a-zа-яё0-9]+/i);
            return words.some((w) => w.startsWith(q));
          })
        : this.languages;

      const selected = filtered.filter((l) => this.query.languages.includes(l.code));
      const rest = filtered.filter((l) => !this.query.languages.includes(l.code));
      return [...selected, ...rest];
    },

    get selectedLanguageObjects() {
      return this.query.languages
        .map((code) => this.languages.find((l) => l.code === code))
        .filter(Boolean);
    },

    focusLanguageSearch(el) {
      // вызывается по нативному событию "toggle" на <details> — то есть
      // именно в момент открытия дропдауна фокус сразу летит в поиск,
      // можно печатать без лишнего клика
      if (el.open) {
        this.languageSearch = "";
        this.$nextTick(() => {
          const input = el.querySelector(".lang-search");
          if (input) input.focus();
        });
      }
    },

    toggleLanguage(code) {
      const isSelected = this.query.languages.includes(code);
      if (isSelected) {
        if (this.query.languages.length === 1) {
          // Нельзя снять последний выбранный язык. Чекбокс в DOM мог уже
          // визуально снять своё состояние (Alpine's :checked не
          // ре-применяется, если само значение query.languages не
          // изменилось) — форсируем реактивность новым массивом с тем же
          // содержимым, чтобы Alpine гарантированно вернул checkbox в
          // состояние checked.
          this.query.languages = [...this.query.languages];
          return;
        }
        this.query.languages = this.query.languages.filter((c) => c !== code);
      } else {
        this.query.languages = [...this.query.languages, code];
      }
    },

    // ---------- Превью-текст ----------

    // Приоритет для дефолтной панграммы: если выбран не только английский
    // (например, добавили cyrillic для русского), берём первый выбранный
    // язык КРОМЕ latin/latin-ext/menu — иначе панграмма так и оставалась
    // бы английской, даже когда пользователь явно добавил русский.
    get previewLanguageCode() {
      const contentLang = this.query.languages.find(
        (c) => c !== "latin" && c !== "latin-ext" && c !== "menu"
      );
      return contentLang || this.query.languages[0] || "latin";
    },

    get defaultPreviewPlaceholder() {
      return DEFAULT_PANGRAMS[this.previewLanguageCode] || FALLBACK_PANGRAM;
    },

    previewTextFor(font) {
      if (this.query.preview_text && this.query.preview_text.trim()) {
        return this.query.preview_text;
      }
      return DEFAULT_PANGRAMS[this.previewLanguageCode] || FALLBACK_PANGRAM;
    },

    // ---------- Динамический @font-face для карточек ----------

    // Бэкенд может отдать regular_woff2_url/bold_woff2_url в двух видах:
    // абсолютный URL (шрифт раздаётся с Google CDN — см. build_database.py)
    // или относительный путь на нашем же бэкенде (/static/fonts/...,
    // фолбэк для шрифтов вне Google Fonts). Склеивать с API_BASE нужно
    // только во втором случае — иначе абсолютный URL будет испорчен
    // (например "http://localhost:8000https://fonts.gstatic.com/...").
    resolveFontUrl(url) {
      if (/^https?:\/\//.test(url)) return url;
      return `${API_BASE}${url}`;
    },

    ensureFontFaceLoaded(font) {
      if (this._injectedFontFaces.has(font.slug)) return;
      this._injectedFontFaces.add(font.slug);

      const familyName = `specimen-${font.slug}`;
      const style = document.createElement("style");
      style.textContent = `
        @font-face {
          font-family: "${familyName}";
          src: url("${this.resolveFontUrl(font.regular_woff2_url)}") format("woff2");
          font-weight: 400;
          font-display: swap;
        }
        @font-face {
          font-family: "${familyName}";
          src: url("${this.resolveFontUrl(font.bold_woff2_url)}") format("woff2");
          font-weight: 700;
          font-display: swap;
        }
      `;
      document.head.appendChild(style);
    },

    cardFontStyle(font) {
      this.ensureFontFaceLoaded(font);
      return { fontFamily: `"specimen-${font.slug}", var(--font-ui)` };
    },

    // ---------- Поиск ----------

    async applySearch() {
      this.loading = true;
      this.errorMessage = "";
      this.fonts = [];
      this.searchId = null;
      this.hasMore = false;

      try {
        const res = await fetch(`${API_BASE}/api/fonts/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: this.query.text || null,
            tags: this.selectedTagIds,
            languages: this.query.languages,
            preview_text: this.query.preview_text || null,
          }),
        });

        if (!res.ok) {
          throw new Error(`search failed: ${res.status}`);
        }

        const data = await res.json();
        this.fonts = data.fonts;
        this.searchId = data.search_id;
        this.hasMore = data.has_more;
        this.hasSearched = true;
      } catch (e) {
        this.errorMessage = "Search failed. Please try again.";
        this.hasSearched = true;
      } finally {
        this.loading = false;
      }
    },

    async loadMore() {
      if (!this.searchId) return;
      this.loadingMore = true;
      this.errorMessage = "";

      try {
        const offset = this.fonts.length;
        const res = await fetch(
          `${API_BASE}/api/fonts/search/${this.searchId}/more?offset=${offset}`
        );

        if (res.status === 404) {
          // раздел 7.4: search_id истёк или сервер перезапустился
          this.errorMessage =
            "Search results have expired. Hit Apply again.";
          this.hasMore = false;
          return;
        }
        if (!res.ok) {
          throw new Error(`more failed: ${res.status}`);
        }

        const data = await res.json();
        this.fonts = [...this.fonts, ...data.fonts];
        this.hasMore = data.has_more;
      } catch (e) {
        this.errorMessage = "Could not load more fonts. Please try again.";
      } finally {
        this.loadingMore = false;
      }
    },
  };
}
