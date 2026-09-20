// Font Matcher — общая Alpine-логика, используется всеми index*.html.
// Разметка/CSS отличаются между вариантами дизайна, эта логика — нет.

const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "";

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
};
const FALLBACK_PANGRAM = "The quick brown fox jumps over the lazy dog";

// ---------------------------------------------------------------------------
// Баннеры (партнёрская реклама). Одна и та же ссылка у всех пяти — отличается
// только картинка, поэтому URL вынесен в константу, а не дублируется.
// rel="sponsored nofollow noopener" — по требованию площадки (Google
// Webmaster Guidelines): партнёрские/рекламные ссылки нужно помечать
// sponsored/nofollow, иначе есть риск санкций для SEO. noopener — обычная
// защита от reverse tabnabbing на любых внешних target="_blank" ссылках.
// ---------------------------------------------------------------------------

const BANNER_HREF = "https://polluxofgeminorum.com/fonts/?id=aleksanderdanilian12";

const BANNER_DEFAULT = {
  id: 1,
  tags: ["vintage", "elegant", "soft", "warm", "friendly", "decorative"],
  img: "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/3hzse0xcm-1773461530823.jpeg",
};

// Порядок в этом списке — приоритет при совпадении нескольких тегов
// одновременно (первый совпавший побеждает). Банер-дефолт проверяется
// последним, как самый широкий catch-all.
const BANNERS = [
  {
    id: 2,
    tags: ["modern", "decorative"],
    img: "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/kxyeit7sv-1773468354999.jpeg",
  },
  {
    id: 3,
    tags: ["minimal", "soft"],
    img: "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/aqjo1wxmn-1773468389086.jpeg",
  },
  {
    id: 4,
    tags: ["friendly"],
    img: "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/k23so07gb-1773468794389.jpeg",
  },
  {
    id: 5,
    tags: ["elegant", "vintage"],
    img: "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/1oj7fao1y-1773468831885.jpeg",
  },
];

// Выбирает баннер по текущим выбранным тегам. Без тегов — всегда дефолт.
// Иначе — первый из BANNERS, у которого пересекаются теги, иначе дефолт
// (если совпал хотя бы один из его тегов), иначе всё равно дефолт — баннер
// показывается всегда, "без баннера" тут не предусмотрено сознательно.
function pickBanner(selectedTagIds) {
  if (!selectedTagIds || selectedTagIds.length === 0) return BANNER_DEFAULT;
  for (const banner of BANNERS) {
    if (banner.tags.some((t) => selectedTagIds.includes(t))) return banner;
  }
  return BANNER_DEFAULT;
}

function fontMatcher() {
  return {
    // --- справочники с бэкенда ---
    tags: [],
    languages: [],
    errorMessage: "",

    // --- состояние формы ---
    query: {
      text: "",
      preview_text: "",
      languages: ["latin"], // дефолт — English
    },
    selectedTagIds: [],
    languageSearch: "",

    // --- результаты поиска ---
    fonts: [],
    searchId: null,
    hasMore: false,
    hasSearched: false,
    loading: false,
    loadingMore: false,
    _injectedFontFaces: new Set(),

    // --- баннер (пересчитывается на каждый Apply, см. applySearch()) ---
    currentBanner: BANNER_DEFAULT,
    bannerHref: BANNER_HREF,

    async init() {
      try {
        const [tagsRes, langsRes] = await Promise.all([
          fetch(`${API_BASE}/api/tags`),
          fetch(`${API_BASE}/api/languages`),
        ]);
        if (!tagsRes.ok || !langsRes.ok) throw new Error("bad response");
        const tagsData = await tagsRes.json();
        const langsData = await langsRes.json();
        this.tags = tagsData.tags;
        this.languages = langsData.languages;
      } catch (e) {
        this.errorMessage =
          "Could not load tags/languages. Check that the backend is running, then reload the page.";
      }
    },

    // ---------- Теги (раздел 4.1: исключающие пары, до 4 одновременно) ----------

    isTagDisabled(tagId) {
      const tag = this.tags.find((t) => t.id === tagId);
      if (!tag) return false;
      if (this.selectedTagIds.includes(tagId)) return false;
      const excludedBySelected = this.selectedTagIds.some((selId) => {
        const selTag = this.tags.find((t) => t.id === selId);
        return selTag && selTag.excludes && selTag.excludes.includes(tagId);
      });
      if (excludedBySelected) return true;
      if (this.selectedTagIds.length >= 4) return true;
      return false;
    },

    toggleTag(tagId) {
      const idx = this.selectedTagIds.indexOf(tagId);
      if (idx >= 0) {
        this.selectedTagIds.splice(idx, 1);
      } else {
        if (this.isTagDisabled(tagId)) return;
        this.selectedTagIds.push(tagId);
      }
    },

    // ---------- Языки (раздел 2, п.4: минимум один всегда выбран) ----------

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
      if (el.open) {
        this.languageSearch = "";
        this.$nextTick(() => {
          const input = el.querySelector(".lang-search");
          if (input) input.focus();
        });
      }
    },

    toggleLanguage(code) {
      const idx = this.query.languages.indexOf(code);
      if (idx >= 0) {
        if (this.query.languages.length === 1) return; // минимум один всегда должен остаться
        this.query.languages.splice(idx, 1);
      } else {
        this.query.languages.push(code);
      }
    },

    // ---------- Превью-текст ----------

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
      this.hasSearched = true;
      // Баннер пересчитывается именно тут — по тегам на МОМЕНТ нажатия
      // Apply, а не реактивно при каждом клике по тегу.
      this.currentBanner = pickBanner(this.selectedTagIds);
      try {
        const res = await fetch(`${API_BASE}/api/fonts/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: this.query.text,
            tags: this.selectedTagIds,
            languages: this.query.languages,
            preview_text: this.query.preview_text,
          }),
        });
        if (!res.ok) throw new Error("search failed");
        const data = await res.json();
        this.fonts = data.fonts;
        this.searchId = data.search_id;
        this.hasMore = data.has_more;
      } catch (e) {
        this.errorMessage = "Search failed. Please try again.";
        this.fonts = [];
        this.hasMore = false;
      } finally {
        this.loading = false;
      }
    },

    async loadMore() {
      if (!this.searchId) return;
      this.loadingMore = true;
      try {
        const offset = this.fonts.length;
        const res = await fetch(
          `${API_BASE}/api/fonts/search/${this.searchId}/more?offset=${offset}`
        );
        if (res.status === 404) {
          this.errorMessage = "Search results have expired. Hit Apply again.";
          this.hasMore = false;
          return;
        }
        if (!res.ok) throw new Error("load more failed");
        const data = await res.json();
        this.fonts = this.fonts.concat(data.fonts);
        this.hasMore = data.has_more;
      } catch (e) {
        this.errorMessage = "Could not load more fonts. Please try again.";
      } finally {
        this.loadingMore = false;
      }
    },

    // ---------- Баннер для разметки: первые 4 карточки / баннер / остальные ----------
    // (см. index.html — рендерится через firstFourFonts -> баннер -> restFonts,
    // так баннер всегда оказывается на 5-й позиции, даже если карточек меньше 4)

    get firstFourFonts() {
      return this.fonts.slice(0, 4);
    },

    get restFonts() {
      return this.fonts.slice(4);
    },
  };
}