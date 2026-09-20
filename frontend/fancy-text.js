// ---------------------------------------------------------------------------
// Social Media Font Generator — Unicode-стили текста.
//
// ВАЖНО, чем это принципиально отличается от каталога шрифтов на главной:
// тут НЕ применяется никакой шрифт. Каждая буква подменяется на ДРУГОЙ
// символ Unicode, который просто выглядит похоже (𝐇 — это не "H жирным
// шрифтом", а отдельный символ MATHEMATICAL BOLD CAPITAL H). Поэтому такой
// текст вставляется куда угодно — в Instagram, TikTok, Twitter — и
// выглядит одинаково: принимающему приложению не нужно знать никакой
// шрифт, для него это обычные символы, как "A" или "1".
//
// Обратная сторона: доступны только те стили, для которых в Unicode
// существуют готовые наборы символов (их около двух десятков) — связать
// это с конкретными шрифтами из каталога (Playfair Display и т.п.)
// невозможно в принципе, для них таких символов не существует.
// ---------------------------------------------------------------------------

const UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const LOWER = "abcdefghijklmnopqrstuvwxyz";
const DIGITS = "0123456789";

// Хелпер: строит карту подстановки из строк-алфавитов. Символы, которых
// нет в карте (пробелы, знаки препинания, кириллица) остаются как есть —
// это осознанно: лучше вернуть частично стилизованный текст, чем потерять
// символы.
function buildMap(upper, lower, digits) {
  const map = {};
  if (upper) [...UPPER].forEach((ch, i) => { const t = [...upper][i]; if (t) map[ch] = t; });
  if (lower) [...LOWER].forEach((ch, i) => { const t = [...lower][i]; if (t) map[ch] = t; });
  if (digits) [...DIGITS].forEach((ch, i) => { const t = [...digits][i]; if (t) map[ch] = t; });
  return map;
}

const STYLES = [
  {
    id: "bold",
    name: "Bold",
    map: buildMap(
      "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙",
      "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
      "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
    ),
  },
  {
    id: "italic",
    name: "Italic",
    map: buildMap(
      "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍",
      "𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧",
      null
    ),
  },
  {
    id: "bold-italic",
    name: "Bold Italic",
    map: buildMap(
      "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁",
      "𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛",
      null
    ),
  },
  {
    id: "script",
    name: "Script",
    map: buildMap(
      "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵",
      "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
      null
    ),
  },
  {
    id: "bold-script",
    name: "Bold Script",
    map: buildMap(
      "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩",
      "𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃",
      null
    ),
  },
  {
    id: "double-struck",
    name: "Outline",
    map: buildMap(
      "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ",
      "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫",
      "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"
    ),
  },
  {
    id: "fraktur",
    name: "Gothic",
    map: buildMap(
      "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ",
      "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷",
      null
    ),
  },
  {
    id: "bold-fraktur",
    name: "Bold Gothic",
    map: buildMap(
      "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅",
      "𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟",
      null
    ),
  },
  {
    id: "monospace",
    name: "Monospace",
    map: buildMap(
      "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉",
      "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣",
      "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
    ),
  },
  {
    id: "sans-bold",
    name: "Sans Bold",
    map: buildMap(
      "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭",
      "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
      "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    ),
  },
  {
    id: "sans-italic",
    name: "Sans Italic",
    map: buildMap(
      "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡",
      "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻",
      null
    ),
  },
  {
    id: "circled",
    name: "Circled",
    map: buildMap(
      "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ",
      "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
      null
    ),
  },
  {
    id: "squared",
    name: "Squared",
    map: buildMap(
      "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉",
      null,
      null
    ),
    uppercaseOnly: true,
  },
  {
    id: "small-caps",
    name: "Small Caps",
    map: buildMap(
      null,
      "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘqʀsᴛᴜᴠwxʏz",
      null
    ),
    uppercaseOnly: false,
    lowercaseSource: true,
  },
  {
    id: "upside-down",
    name: "Upside Down",
    map: buildMap(
      "∀ᙠƆpƎℲƃHIſʞ˥WNOԀQɹS┴∩ΛMX⅄Z",
      "ɐqɔpǝɟƃɥıɾʞlɯuodbɹsʇnʌʍxʎz",
      null
    ),
    reverse: true,
  },
  {
    id: "wide",
    name: "Wide",
    map: buildMap(
      "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
      "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
      "０１２３４５６７８９"
    ),
  },
  {
    id: "circled-filled",
    name: "Circled Filled",
    map: buildMap(
      "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩",
      null,
      null
    ),
    uppercaseOnly: true,
  },
  {
    id: "squared-filled",
    name: "Squared Filled",
    map: buildMap(
      "🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉",
      null,
      null
    ),
    uppercaseOnly: true,
  },
  {
    id: "superscript",
    name: "Superscript",
    map: buildMap(
      "ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾQᴿˢᵀᵁⱽᵂˣʸᶻ",
      "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖqʳˢᵗᵘᵛʷˣʸᶻ",
      "⁰¹²³⁴⁵⁶⁷⁸⁹"
    ),
  },
  {
    id: "subscript",
    name: "Subscript",
    map: buildMap(
      null,
      "ₐbcdₑfgₕᵢⱼₖₗₘₙₒₚqᵣₛₜᵤᵥwₓyz",
      "₀₁₂₃₄₅₆₇₈₉"
    ),
    lowercaseSource: true,
  },
  {
    // Комбинирующие символы (U+0336 и т.п.) добавляются ПОСЛЕ каждой буквы,
    // а не подменяют её — поэтому это не map, а отдельный combining-режим.
    id: "strikethrough",
    name: "Strikethrough",
    combining: "\u0336",
  },
  {
    id: "underline",
    name: "Underline",
    combining: "\u0332",
  },
  {
    id: "slashthrough",
    name: "Slash Through",
    combining: "\u0338",
  },
];

function transformText(text, style) {
  if (!text) return "";

  // Combining-стили (зачёркнутый, подчёркнутый) работают иначе: они не
  // подменяют букву другим символом, а ДОБАВЛЯЮТ к ней невидимый
  // combining-символ, который браузер отрисовывает поверх. Поэтому
  // сохраняются любые буквы — включая кириллицу, в отличие от map-стилей.
  if (style.combining) {
    return [...text].map((ch) => (ch === " " ? ch : ch + style.combining)).join("");
  }

  let source = text;
  // Squared-стиль существует в Unicode только в верхнем регистре —
  // приводим ввод, иначе строчные буквы просто не преобразуются.
  if (style.uppercaseOnly) source = source.toUpperCase();
  // Small caps наоборот: набор есть только для строчных форм.
  if (style.lowercaseSource) source = source.toLowerCase();

  let out = [...source].map((ch) => style.map[ch] || ch).join("");
  // "Перевёрнутый" стиль требует ещё и обратного порядка символов,
  // иначе текст читается задом наперёд.
  if (style.reverse) out = [...out].reverse().join("");
  return out;
}

function fancyText() {
  return {
    input: "",
    styles: STYLES,
    copiedId: null,
    bannerHref: "https://polluxofgeminorum.com/fonts/?id=aleksanderdanilian12",
    bannerImg:
      "https://qnthgdfusotvjgaxpfie.supabase.co/storage/v1/object/public/assets/d20b9219-fb9e-4c55-a60c-e033adc2dd89/3hzse0xcm-1773461530823.jpeg",

    get placeholderPreview() {
      return "Type something above";
    },

    outputFor(style) {
      const text = this.input.trim();
      if (!text) return transformText("Your text here", style);
      return transformText(text, style);
    },

    get hasInput() {
      return this.input.trim().length > 0;
    },

    async copy(style) {
      const text = this.outputFor(style);
      try {
        await navigator.clipboard.writeText(text);
        this.copiedId = style.id;
        setTimeout(() => {
          if (this.copiedId === style.id) this.copiedId = null;
        }, 1600);
      } catch (e) {
        // Fallback для браузеров/контекстов без Clipboard API (например,
        // если страница вдруг открыта не по https): временный textarea +
        // execCommand — устаревший способ, но всё ещё работает везде.
        try {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
          this.copiedId = style.id;
          setTimeout(() => {
            if (this.copiedId === style.id) this.copiedId = null;
          }, 1600);
        } catch (e2) {
          alert("Could not copy — please select the text and copy manually.");
        }
      }
    },
  };
}