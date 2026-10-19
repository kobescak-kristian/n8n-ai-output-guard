"""JavaScript of the guard's prompt-injection check (CASES.md rule 6 and section 3b).

Design (after two code red teams, 2026-10-19): not a list of exact phrases but word families
in many languages, each family tied to a context that separates an order to the AI from normal
customer text. The input is normalised first (white space collapsed, markdown stars and quote
markers removed), so no pattern can backtrack over long white-space runs. Every pattern uses
Unicode word edges (the u flag).

Signals (any one gives a hit):
  ignore family     ignore/forget/disregard (+ "do not follow", "pay no attention to") + only filler
                    words + instructions/rules/prompt..., unless the words after it show the
                    customer's own instructions ("I sent", "regarding my address", "in the manual")
  role line         SYSTEM: / Assistant: / [system] / {{system}} ... when the rest is an order
  tags              <<SYS>>, [INST], <|system|>, </system>, ### Instruction, # Instructions heading
  identity          you are now / no longer / pretend / roleplay / your new role + an AI word
  mode              developer/admin/debug/god/jailbreak mode switched on, as an order
  field order       an order verb + a schema field + a value allowed for that field, or "field":
  fixed answer      return/respond/use ... + a JSON object with a key, or "expected output: {"
  addressed to AI   "Hey ChatGPT," / "Note to the AI:" ... + an order or a field value
  comment to AI     <!-- ... assistant / AI / bot / LLM ... -->
  new instructions  "new instructions:" + a schema field or an order
"""

INJECT = r"""
// ---------- prompt-injection check (CASES.md rule 6 and 3b) ----------
const EB = '(?<![\\p{L}\\p{N}_])';
const EE = '(?![\\p{L}\\p{N}_])';
const alt = (a) => a.join('|');
const RX = (src, flags) => { const f = flags || 'i'; return new RegExp(src, f.includes('u') ? f : f + 'u'); };
const word = (a) => EB + '(?:' + alt(a) + ')' + EE;

function normText(t) {
  return String(t).replace(/\r/g, '').replace(/[*`]+/g, '').replace(/^[ \t]*(>[ \t]?)+/gm, '')
    .replace(/[ \t  -​　]+/g, ' ').replace(/ ?\n ?/g, '\n').replace(/\n{2,}/g, '\n').trim();
}

// order verbs (imperative) in the covered languages
const IMP = ['set', 'put', 'mark', 'make', 'change', 'classify', 'categori[sz]e', 'assign', 'give', 'rate', 'score',
  'escalate', 'flag', 'treat', 'respond', 'reply', 'answer', 'output', 'return', 'write', 'ignore', 'forget',
  'disregard', 'skip', 'stop', 'label', 'route', 'prioriti[sz]e', 'override', 'bypass', 'enable', 'activate',
  'switch', 'enter', 'act', 'behave', 'pretend', 'roleplay', 'print', 'say', 'tell', 'consider', 'use', 'do not',
  "don't", 'from now on',
  'setze', 'setzen sie', 'stelle', 'markiere', 'ändere', 'gib', 'antworte', 'ignoriere', 'vergiss', 'behandle',
  'klassifiziere', 'verwende', 'schreibe', 'aktiviere', 'ab jetzt', 'von jetzt an',
  'mets', 'mettez', 'marque', 'marquez', 'définis', 'définissez', 'changez', 'réponds', 'répondez', 'ignorez',
  'oublie', 'oubliez', 'classe', 'classez', 'donne', 'donnez', 'utilise', 'utilisez', 'écris', 'écrivez', 'activez',
  'renvoie', 'renvoyez', 'désormais', 'à partir de maintenant',
  'pon', 'ponga', 'marca', 'cambia', 'cambie', 'responde', 'responda', 'ignora', 'olvida', 'olvide', 'clasifica',
  'clasifique', 'asigna', 'asigne', 'devuelve', 'devuelva', 'escribe', 'activa', 'establece', 'establezca',
  'a partir de ahora',
  'imposta', 'metti', 'segna', 'rispondi', 'dimentica', 'classifica', 'assegna', 'restituisci', 'scrivi', 'attiva',
  "d'ora in poi",
  'defina', 'coloque', 'mude', 'esqueça', 'classifique', 'atribua', 'retorne', 'escreva', 'ative',
  'zet', 'markeer', 'wijzig', 'geef', 'negeer', 'vergeet', 'gebruik',
  'установи', 'поставь', 'отметь', 'измени', 'ответь', 'игнорируй', 'забудь', 'используй', 'присвой',
  'ustaw', 'oznacz', 'zmień', 'odpowiedz', 'zignoruj', 'zapomnij', 'postavi', 'označi', 'promijeni', 'odgovori',
  'zanemari', 'zaboravi'];
const IMP_RX = RX(word(IMP));
const IMP_START = RX('^\\s*(?:please\\s+|kindly\\s+|bitte\\s+|merci de\\s+|por favor,?\\s+|per favore,?\\s+)?' + word(IMP) + '(?:\\s+(\\S+))?');
const OBJECT_WORDS = /^(?:This|It|That|The|All|Every|Each|These|Those|Priority|Urgency|Category|Me|Us)$/;
// an order at the start of a clause; "Mark Peters" (verb-like first name + a capitalised word) is not an order
function startsWithOrder(s) {
  const m = IMP_START.exec(s);
  if (!m) return false;
  const next = m[1] || '';
  return !(/^\p{Lu}\p{Ll}/u.test(next) && !OBJECT_WORDS.test(next.replace(/[^\p{L}]/gu, '')));
}

// ignore family: verb + only filler words + an instruction word, per language
const IGNORE = [
  // [verbs, fillers, nouns]
  [['ignore', 'disregard', 'forget', 'override', 'bypass', 'skip', 'discard', 'drop', 'abandon', 'do not follow',
    "don't follow", 'stop following', 'no longer follow', 'pay no attention to', 'do not obey', "don't obey"],
   ['all', 'any', 'and', 'every', 'the', 'your', 'previous', 'prior', 'above', 'earlier', 'preceding', 'original',
    'initial', 'system', 'of', 'these', 'those', 'what', 'you', 'were', 'have', 'been', 'given', 'told', 'before',
    'old', 'existing', 'current', 'safety', 'default', 'other'],
   ['instructions?', 'rules?', 'prompts?', 'guidelines?', 'directions?', 'directives?', 'commands?', 'guidance',
    'programming', 'guardrails?', 'restrictions?', 'system prompt', 'policies', 'text above', 'messages? above',
    'previous messages?', 'everything above', 'context']],
  [['ignoriere', 'ignorier', 'ignorieren sie', 'vergiss', 'vergessen sie', 'missachte', 'missachten sie', 'übergehe',
    'überspringe'],
   ['alle', 'sämtliche', 'die', 'den', 'deine', 'ihre', 'bisherigen', 'vorherigen', 'vorhergehenden', 'vorigen',
    'obigen', 'früheren', 'vorangegangenen', 'ursprünglichen', 'oben', 'genannten'],
   ['anweisungen', 'anweisung', 'instruktionen', 'regeln', 'befehle', 'vorgaben', 'systemprompt', 'system-prompt',
    'systemanweisungen']],
  [['ignore', 'ignorez', 'oublie', 'oubliez', 'ne tiens pas compte des?', 'ne tenez pas compte des?',
    'fais abstraction des?', 'faites abstraction des?', 'ne suis pas', 'ne suivez pas'],
   ['toutes', 'tous', 'les', 'des', "l'ensemble", 'de', 'vos', 'tes', 'précédentes', 'précédents', 'ci-dessus',
    'anciennes', "d'", 'ces'],
   ['instructions', 'consignes', 'règles', 'directives', 'commandes', 'ordres']],
  [['ignora', 'ignore', 'ignoren', 'olvida', 'olvide', 'olviden', 'omite', 'omita', 'haz caso omiso (?:de|a)',
    'no hagas caso (?:de|a)', 'no haga caso (?:de|a)', 'no sigas', 'no siga'],
   ['todas', 'todos', 'las', 'los', 'tus', 'sus', 'anteriores', 'previas', 'de', 'a', 'estas', 'esas'],
   ['instrucciones', 'reglas', 'indicaciones', 'órdenes', 'normas', 'comandos']],
  [['ignora', 'ignorate', 'ignori', 'dimentica', 'dimenticate', 'non seguire', 'non seguite', 'trascura'],
   ['tutte', 'tutti', 'le', 'i', 'gli', 'tue', 'vostre', 'precedenti', 'sopra'],
   ['istruzioni', 'regole', 'indicazioni', 'comandi', 'ordini']],
  [['ignore', 'ignora', 'ignorem', 'esqueça', 'esqueca', 'esqueçam', 'desconsidere', 'desconsiderem', 'não siga',
    'nao siga'],
   ['todas', 'todos', 'as', 'os', 'suas', 'tuas', 'anteriores', 'prévias', 'acima'],
   ['instruções', 'instrucoes', 'regras', 'orientações', 'comandos']],
  [['negeer', 'vergeet'], ['alle', 'de', 'je', 'jouw', 'vorige', 'eerdere', 'voorgaande', 'bovenstaande'],
   ['instructies', 'regels', 'opdrachten', 'aanwijzingen']],
  [['zignoruj', 'ignoruj', 'zapomnij', 'zapomnij o'],
   ['wszystkie', 'wszystkich', 'poprzednie', 'poprzednich', 'wcześniejsze', 'wcześniejszych', 'powyższe', 'swoje'],
   ['instrukcje', 'instrukcjach', 'instrukcji', 'polecenia', 'poleceniach', 'zasady', 'reguły']],
  [['zanemari', 'zanemarite', 'ignoriraj', 'ignorirajte', 'ignoriši', 'zaboravi', 'zaboravite'],
   ['sve', 'prethodne', 'prethodna', 'ranije', 'svoje', 'gornje'],
   ['upute', 'uputstva', 'naredbe', 'instrukcije', 'pravila']],
  [['занемари', 'игнориши', 'заборави', 'игнорируй', 'игнорируйте', 'проигнорируй', 'проигнорируйте', 'забудь',
    'забудьте', 'не обращай внимания на', 'не обращайте внимания на', 'не следуй', 'ігноруй', 'ігноруйте'],
   ['све', 'претходна', 'претходне', 'все', 'всё', 'предыдущие', 'прежние', 'свои', 'вышеуказанные', 'всі',
    'попередні'],
   ['упутства', 'упуте', 'наредбе', 'правила', 'инструкције', 'инструкции', 'указания', 'команды', 'інструкції',
    'вказівки']],
  [['ignoruj', 'ignorujte', 'zapomeň', 'zapomeňte', 'zabudni', 'zabudnite'],
   ['všechny', 'všetky', 'předchozí', 'predchádzajúce', 'předešlé', 'predošlé'],
   ['pokyny', 'instrukce', 'inštrukcie', 'pravidla', 'pravidlá']],
  [['ignorera', 'glöm', 'ignorer', 'glem', 'unohda', 'ohita', 'älä noudata', 'ignoră', 'ignorați', 'uită',
    'abaikan', 'lupakan', 'puuza', 'sahau', 'αγνόησε', 'αγνοήστε', 'ξέχασε'],
   ['alla', 'alle', 'tidigare', 'de', 'föregående', 'forrige', 'tidligere', 'kaikki', 'aiemmat', 'edelliset', 'toate',
    'semua', 'yote', 'τις', 'όλες', 'προηγούμενες'],
   ['instruktioner', 'instruksjoner', 'instruktionerne', 'regler', 'anvisningar', 'ohjeet', 'säännöt',
    'instrucțiunile', 'regulile', 'instruksi', 'perintah', 'aturan', 'petunjuk', 'maagizo', 'maelekezo', 'sheria',
    'οδηγίες', 'κανόνες']],
];
const IGNORE_RX = IGNORE.map(([v, f, n]) =>
  RX(EB + '(?:' + alt(v) + ')(?:\\s+(?:' + alt(f) + '))*?\\s+(?:' + alt(n) + ')' + EE));
// limit filler words to 6 (checked after the match)
const OWN = RX('^\\s*,?\\s*(?:(?:that\\s+)?(?:i|we|ich|wir|je|nous|yo|io|eu)\\s+(?:sent|gave|wrote|made|left|had|mentioned|added|put|schickte|gab|schrieb|ai|avons)'
  + '|(?:regarding|about|concerning|for|on|in|from|of|with|zur|zum|über|für|in der|im|sur|pour|dans|sobre|para|en|de|su|sulla|nel|per)\\s+(?:my|our|the|your|this|mein\\w*|unser\\w*|die|der|den|dem|ihr\\w*|le|la|les|mes|mon|ma|notre|mi|mis|el|los|las|il|lo|i|gli|meu|minha|o|a)\\s+(?:own\\s+)?(?:address|delivery|deliveries|order|parcel|package|return|refund|account|courier|driver|door|manual|website|site|guide|faq|box|leaflet|letter|e-?mail|mail|invoice|booking|tenant|adresse|lieferung|bestellung|paket|anleitung|livraison|commande|colis|notice|dirección|entrega|pedido|paquete|manual|indirizzo|consegna|ordine|pacco|endereço|encomenda)'
  + '|(?:the|der|die|le|la|el|il)\\s+(?:courier|driver|delivery|kurier|fahrer|livreur|repartidor|corriere|door|tür|porte|puerta))');
const IGNORE_EXTRA = [
  RX(EB + '(?:ignore|disregard|forget)\\s+(?:all\\s+(?:of\\s+)?)?(?:the\\s+)?(?:above|previous|preceding|foregoing)\\s+(?:text\\s+|messages?\\s+)?(?:and|then|,)\\s+(?:\\S+\\s+){0,2}?' + word(IMP)),
  RX(EB + '(?:forget|ignore|disregard)\\s+(?:everything|all)\\s+(?:you\\s+(?:were|have\\s+been)\\s+told|above|before|so\\s+far)' + EE),
  RX(EB + '(?:forget|ignore|disregard)\\s+(?:everything\\s+|all\\s+)?what\\s+you\\s+(?:were|have\\s+been)\\s+(?:told|given)' + EE),
  RX(EB + 'vergiss\\s+alles\\s*,?\\s+(?:was\\s+(?:dir|man\\s+dir)|davor|bisher|oben)'),
  RX(EB + 'oublie[zr]?\\s+tout\\s+(?:ce\\s+qu.on\\s+t.a\\s+dit|ce\\s+qui\\s+précède|avant)'),
  RX(EB + '(?:olvida|olvide|ignora|ignore)\\s+(?:todo\\s+)?lo\\s+(?:anterior|dicho)(?!\\s+que\\s+(?:te|le)\\s+(?:escrib|dij|mand))'),
  RX(EB + 'beachte\\s+(?:die\\s+|alle\\s+)?(?:vorherigen\\s+|bisherigen\\s+|obigen\\s+)?(?:anweisungen|regeln)\\s+nicht' + EE),
  RX(EB + '(?:hagyd\\s+figyelmen\\s+kívül|felejtsd\\s+el)\\s+(?:a\\s+)?(?:korábbi\\s+|előző\\s+|összes\\s+)?(?:utasításokat|szabályokat)'),
  RX('(?:önceki|tüm|bütün|yukarıdaki)\\s+(?:talimatları|talimatlarını|kuralları|komutları)\\s+(?:yok\\s+say|unut|görmezden\\s+gel|dikkate\\s+alma)'),
  RX('(?:تجاهل|انس|تجاهلي)\\s+(?:كل|جميع)?\\s*(?:التعليمات|الأوامر|القواعد)'),
  RX('(?:पिछले|सभी|पूर्व|पहले)[^।.\\n]{0,20}(?:निर्देशों|निर्देश)[^।.\\n]{0,20}(?:अनदेखा|नज़रअंदाज़|नजरअंदाज|भूल)'),
  RX('(?:이전|위의|모든)?\\s*(?:지시|지침|명령|규칙)(?:를|을|은|는)?\\s*(?:모두\\s*)?(?:무시|잊어)'),
  RX('(?:bỏ\\s+qua|phớt\\s+lờ|quên)\\s+(?:tất\\s+cả\\s+)?(?:các\\s+)?(?:hướng\\s+dẫn|chỉ\\s+dẫn|quy\\s+tắc|lệnh)'),
  RX('(?:忽略|无视|忘记|忘掉|忽視|無視|忘記)(?:掉)?(?:之前|以上|前面|先前|上面|上述)?(?:的)?(?:所有|全部)?(?:的)?(?:指令|指示|说明|說明|规则|規則|提示|系统提示|系統提示)'),
  RX('(?:以前|これまで|上記|前|上)の(?:すべての|全ての)?(?:指示|命令|ルール|指令)(?:は|を)(?:すべて|全て)?(?:無視|忘れ)'),
];

function ignoreHit(t) {
  const all = IGNORE_RX.map((re) => [re, true]).concat(IGNORE_EXTRA.map((re) => [re, false]));
  for (const [re, counted] of all) {
    const g = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
    let m;
    while ((m = g.exec(t)) !== null) {
      const words = m[0].trim().split(/\s+/).length;
      const after = t.slice(m.index + m[0].length, m.index + m[0].length + 80);
      if ((!counted || words <= 9) && !OWN.test(after)) return true;
      g.lastIndex = m.index + 1;
    }
  }
  return false;
}

// AI words, for identity switches and addresses
const AI_NOUN = '(?:ai|a\\.i\\.|bot|\\p{L}*bot|robot|assistant|assistent|asistente|assistente|asystent|asistent|model|modell|modelo|modello|modèle|engine|classifier|classificateur|clasificador|classificatore|triage\\s+\\p{L}+|gpt|chatgpt|dan|llm|chatbot|ki|ia|бот|ассистент|модель|program|machine)';
const RULE_WORDS = '(?:(?:no|without|free\\s+of|ohne|sans|sin|senza|sem)\\s+(?:any\\s+)?(?:rules|restrictions|limits|filters|guidelines|regeln|règles|reglas|regole|regras))';
const TIME_AFTER = '(?!(?:an?|the|one|two|three)\\s+(?:\\p{L}+\\s+)?(?:week|day|hour|month|minute|year)s?\\b)';
const IDENTITY = [
  RX(EB + "(?:you\\s+are|you're|you\\s+will\\s+be)\\s+now\\s+" + TIME_AFTER + "(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}\\d.-]+\\s+){0,3}?" + AI_NOUN + EE),
  RX(EB + "now\\s+(?:you\\s+are|you're)\\s+(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}\\d.-]+\\s+){0,3}?" + AI_NOUN + EE),
  RX(EB + "you\\s+are\\s+no\\s+longer\\s+(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}-]+\\s+){0,2}?" + AI_NOUN + EE),
  RX(EB + "(?:you\\s+are|you're)\\s+now\\s+[^.!?\\n]{0,40}?" + RULE_WORDS),
  RX("\\b[Yy]ou\\s+are\\s+now\\s+[A-Z][\\w-]*(?:\\s*\\d[\\d.]*)?\\s*(?:[,.]\\s*)?(?:an?\\s+(?:AI|ai|bot|assistant|model)\\b|without\\b|with\\s+no\\b|and\\s+you\\b)", 'u'),
  RX(EB + "(?:you\\s+are|you're)\\s+now\\s+(?:in|entering)\\s+(?:\\p{L}+\\s+){0,2}?(?:developer|admin|god|debug|jailbreak|dan|unrestricted|sudo|root|maintenance)\\s+mode" + EE),
  RX(EB + "(?:you\\s+are|you're)\\s+now\\s+(?:acting|playing|operating|working)\\s+as" + EE),
  RX(EB + "(?:pretend|imagine)\\s+(?:that\\s+)?(?:you\\s+are|you're|to\\s+be)\\s+[^.!?\\n]{0,40}?(?:" + AI_NOUN + "|" + RULE_WORDS + ")" + EE),
  RX(EB + "(?:roleplay|role-play|role\\s+play)\\s+as\\s+[^.!?\\n]{0,40}?(?:" + AI_NOUN + "|" + RULE_WORDS + ")" + EE),
  RX(EB + "(?:act|behave|respond|answer)\\s+(?:as|like)\\s+(?:an?\\s+|the\\s+)?(?:(?:unrestricted|uncensored|unfiltered|different|new|other|evil|jailbroken|free)\\s+)(?:" + AI_NOUN + ")" + EE),
  RX(EB + "(?:act|behave)\\s+as\\s+(?:an?\\s+|the\\s+)?" + AI_NOUN + "\\s+(?:with\\s+no|without)\\s+(?:rules|restrictions|limits|filters)"),
  RX(EB + "your\\s+new\\s+(?:role|job|task|purpose|instructions?)\\s+(?:is|are|:)"),
  RX(EB + "(?:here\\s+are|these\\s+are)\\s+(?:your|the)\\s+new\\s+instructions?"),
  RX(EB + "from\\s+now\\s+on\\s*,?\\s+(?:you\\s+are|you're|you\\s+will|you'll|you\\s+must|you\\s+should)\\s+(?:(?:an?|the)\\s+)?(?:[\\p{L}-]+\\s+){0,3}?(?:" + AI_NOUN + "|only\\s+(?:answer|respond|reply|output)|answer|respond|reply|output|ignore|mark|set|classify)" + EE),
  RX(EB + "(?:du\\s+bist\\s+(?:jetzt|nun|ab\\s+jetzt)|ab\\s+jetzt\\s+bist\\s+du|tu\\s+es\\s+(?:maintenant|désormais)|désormais\\s+tu\\s+es|vous\\s+êtes\\s+(?:maintenant|désormais)|ahora\\s+eres|ahora\\s+es\\s+usted|a\\s+partir\\s+de\\s+ahora\\s+eres|ora\\s+sei|adesso\\s+sei|d'ora\\s+in\\s+poi\\s+sei|agora\\s+(?:você\\s+é|tu\\s+és|és)|jij\\s+bent\\s+nu|je\\s+bent\\s+nu|teraz\\s+jesteś|sada\\s+si|теперь\\s+ты)\\s+(?:[^.!?\\n]{0,30}?\\s)?" + AI_NOUN + EE),
];

// tags, headings and comments
const TAGS = [
  /<<\/?SYS>>/i, /<\|(?:system|user|assistant|im_start|im_end)\|>/i, /\[\/?(?:SYSTEM|INST)\]/i,
  /\{\{\s*system\s*\}\}/i, /<\/?\s*(?:system|assistant|instructions?)\s*>/i, /\[system\]\(#/i,
  RX('#{1,6} ?(?:new\\s+)?(?:system\\s+)?instructions?' + EE),
  RX('(?:^|\\n)#{1,6} ?response\\s*:'),
  RX('<!--[^>]{0,300}?' + EB + '(?:assistant|ai|a\\.i\\.|bot|llm|claude|gpt|chatgpt|model|instructions?)' + EE + '[^>]{0,300}?-->'),
];

// attack modes switched on
const MODE = '(?:developer|admin|administrator|debug|god|jailbreak|dan|unrestricted|sudo|root|maintenance)\\s+mode';
const MODES = [
  RX(EB + MODE + '\\s*:'),
  RX('(?:^|\\n|[.!?;]\\s)\\s*(?:please\\s+)?(?:enable|activate|enter|switch\\s+(?:in)?to|turn\\s+on|go\\s+into)\\s+(?:the\\s+|your\\s+)?' + MODE + EE),
  RX(EB + MODE + '\\s+(?:is\\s+)?(?:now\\s+)?(?:on|enabled|activated|active)\\s*(?:[.!]|$|\\n)'),
  RX(EB + '(?:god|jailbreak|dan|unrestricted|sudo)\\s+mode' + EE),
  RX('(?:modo\\s+(?:de\\s+)?desarrollador|modalità\\s+sviluppatore|mode\\s+développeur|entwicklermodus|modo\\s+(?:de\\s+)?desenvolvedor|ontwikkelaarsmodus|tryb\\s+dewelopera|режим\\s+разработчика)(?:\\s*:|\\s+(?:activado|activada|attivata|attivo|activé|aktiviert|ativado|geactiveerd|aktywny|включ\\S*)\\s*(?:[.!:]|$|\\n))'),
  RX('(?:^|\\n|[.!?;]\\s)\\s*(?:aktiviere|activa|attiva|active|activez|ative|włącz)\\s+(?:den\\s+|el\\s+|la\\s+|le\\s+|o\\s+)?(?:entwicklermodus|modo\\s+(?:de\\s+)?desarrollador|modalità\\s+sviluppatore|mode\\s+développeur|modo\\s+(?:de\\s+)?desenvolvedor|tryb\\s+dewelopera)'),
];

// field orders: an order verb + a schema field + a value that field allows
const FIELD_TR = {
  priority: ['priorität', 'priorite', 'priorité', 'prioridad', 'priorità', 'prioridade', 'prioriteit', 'priorytet',
    'prioritet', 'приоритет'],
  urgency: ['dringlichkeit', 'urgence', 'urgencia', 'urgenza', 'urgência'],
  category: ['kategorie', 'catégorie', 'categoría', 'categoria', 'categorie', 'kategoria', 'категорию', 'категория'],
};
const VALUE_TR = ['niedrig', 'hoch', 'dringend', 'basse', 'bas', 'haute', 'élevée', 'urgente', 'baja', 'alta', 'bassa',
  'baixa', 'laag', 'hoog', 'niski', 'wysoki', 'nizak', 'visok', 'низкий', 'высокий', 'срочный', 'normale', 'normal'];
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function fieldRegexes(schema) {
  const props = (schema && schema.properties) || {};
  const out = [];
  for (const [k, s] of Object.entries(props)) {
    const names = [esc(k)];
    if (k.includes('_')) names.push(esc(k).replace(/_/g, '[\\s_-]+'));
    for (const tr of FIELD_TR[k] || []) names.push(tr);
    const types = Array.isArray(s.type) ? s.type : [s.type];
    const values = [];
    if (Array.isArray(s.enum)) values.push(...s.enum.filter((x) => typeof x === 'string').map(esc));
    if (types.includes('boolean')) values.push('true', 'false', 'yes', 'no', 'wahr', 'falsch', 'vrai', 'faux', 'verdadero', 'falso', 'vero', 'verdadeiro');
    if (types.includes('number') || types.includes('integer')) values.push('-?\\d+(?:[.,]\\d+)?', 'zero', 'null', 'none');
    if (FIELD_TR[k]) values.push(...VALUE_TR);
    if (!values.length) continue;
    const F = '(?:' + names.join('|') + ')';
    const V = '(?:' + values.join('|') + ')';
    out.push(RX(EB + '(?:' + alt(IMP) + ')' + EE + '[^.!?\\n]{0,40}?' + EB + F + EE + '[^.!?\\n]{0,25}?' + EB + V + EE));
    out.push(RX(EB + '(?:' + alt(IMP) + ')' + EE + '[^.!?\\n]{0,40}?' + EB + V + EE + '\\s+' + F + EE));
    out.push(RX(EB + F + EE + '\\s*(?:=|is|should\\s+be|must\\s+be|to|as|of|:)\\s*"?' + V + EE));
  }
  return out;
}

function keyRegex(schema) {
  const keys = Object.keys((schema && schema.properties) || {}).map(esc);
  return keys.length ? RX('"(?:' + keys.join('|') + ')"\\s*:') : null;
}

const FIXED = [
  RX(EB + '(?:return|respond|reply|answer|output|use|give|print|write|send\\s+back|devuelve|devuelva|responde|responda|retorne|retorna|restituisci|rispondi|renvoie|renvoyez|réponds|répondez|gib|antworte|verwende|usa|utilise)' + EE + '[\\s\\S]{0,80}?\\{\\s*"[^"\\n]{1,40}"\\s*:'),
  RX(EB + '(?:correct|expected|right|desired|required|final)\\s+(?:output|answer|json|response|result)' + EE + '\\s*(?:is|:|=)?\\s*\\{'),
  RX(EB + '(?:your|the)\\s+(?:answer|response|output|reply|json)\\s+(?:must|should|has\\s+to)\\s+be\\s+(?:exactly\\s+)?(?:this\\s*:?\\s*)?\\{'),
  RX(EB + '(?:return|respond|reply|answer|output)' + EE + '[^.!?\\n]{0,40}?' + EB + '(?:exactly|only|this|the\\s+following)' + EE + '[\\s\\S]{0,40}?\\{\\s*"'),
];

const ADDRESS = [
  RX('(?:^|\\n|[.!?;]\\s|,\\s)\\s*(?:hey|hi|hello|dear|attention|ok)?\\s*,?\\s*(?:chatgpt|chat\\s+gpt|gpt|gemini|copilot|claude|llm|ai|a\\.i\\.|bot|chatbot|assistant)\\s*[:,]'),
  RX(EB + '(?:note|message|instructions?|important(?:\\s+\\p{L}+){0,2})\\s+(?:to|for)\\s+(?:the\\s+|any\\s+)?(?:ai(?:\\s+model)?|a\\.i\\.|language\\s+model|llm|bot|chatbot|assistant|model|chatgpt|gpt|claude|gemini|copilot)' + EE),
  RX(EB + '(?:to|for|dear|hey|hi)\\s+(?:the\\s+|any\\s+)?(?:ai(?:\\s+model)?|language\\s+model|llm|chatgpt|gpt)\\s+(?:(?:reading|processing|that\\s+reads|that\\s+processes)\\s+this\\s*)?[:,]'),
];

const ROLE = '(?:system|assistant|developer|admin|administrator|operator|sys|root|override|sistema|système|systeme|systemnachricht|system-nachricht|система|システム|系统|系統)';
const ROLE_QUAL = '(?:message|prompt|override|note|notice|instructions?|alert|update|command|nachricht|mensaje|messaggio)';
const ROLE_RX = [
  RX('(?:\\[|\\(|<|\\{\\{)\\s?(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s?(?:\\]|\\)|>|\\}\\})\\s?:?([^\\n]{0,160})', 'gi'),
  RX(EB + '(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s?[:：]([^\\n]{0,160})', 'gi'),
  RX(EB + '(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s[-–—]{1,2}\\s([^\\n]{0,160})', 'gi'),
];
const RULES_OFF = RX('(?:rules|instructions|restrictions|guidelines)\\s+(?:no\\s+longer|do\\s+not|don.t)\\s+apply|' + EB + '(?:this|the)\\s+(?:ticket|claim|lead|message|e-?mail|request|case)\\s+is\\s+(?:not\\s+)?\\p{L}');

function isOrder(rest, F, KEY) {
  const r = rest.split(/(?<=[.!?])\s/)[0];
  return startsWithOrder(r) || RULES_OFF.test(r) || F.some((re, i) => i % 3 !== 2 && re.test(rest)) ||
    (KEY && KEY.test(rest)) || /\{\s*"|\b\w+\s*=\s*\S/.test(rest) || ignoreHit(rest) ||
    IDENTITY.some((re) => re.test(rest)) || RX(EB + "(?:you\\s+are\\s+now|you're\\s+now)" + EE).test(r);
}

function roleHit(t, F, KEY) {
  for (const re of ROLE_RX) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(t)) !== null) {
      const role = m[1], qual = (m[2] || '').toLowerCase(), rest = m[3] || '';
      const before = t.slice(Math.max(0, m.index - 2), m.index);
      const start = m.index === 0 || /[\n.!?;(\[{<-]\s?$|^\s?$/.test(before) || /^[\n]/.test(before.slice(-1));
      const caps = role === role.toUpperCase() && /\p{Lu}/u.test(role);
      const bracket = /^[\[(<{]/.test(m[0]);
      if (start || caps || bracket) {
        if (/override|instruction|command/.test(qual) || /^override$/i.test(role) || isOrder(rest, F, KEY)) return true;
      }
      if (m.index === re.lastIndex) re.lastIndex++;
    }
  }
  return false;
}

function stringsIn(v, out) {
  out = out || [];
  if (typeof v === 'string') out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => stringsIn(x, out));
  else if (isObj(v)) Object.values(v).forEach((x) => stringsIn(x, out));
  return out;
}

function injectionHits(input, schema) {
  const t = normText(stringsIn(input).join('\n'));
  const F = fieldRegexes(schema);
  const KEY = keyRegex(schema);
  const hits = [];
  if (ignoreHit(t)) hits.push('ignore earlier instructions');
  if (roleHit(t, F, KEY)) hits.push('role line');
  if (TAGS.some((re) => re.test(t))) hits.push('role tag or comment');
  if (IDENTITY.some((re) => re.test(t))) hits.push('identity switch');
  if (MODES.some((re) => re.test(t))) hits.push('mode switch');
  if (F.slice().filter((_, i) => i % 3 !== 2).some((re) => re.test(t)) || (KEY && KEY.test(t))) hits.push('field order');
  if (FIXED.some((re) => re.test(t))) hits.push('fixed answer');
  if (ADDRESS.some((re) => re.test(t))) {
    const declared = F.filter((_, i) => i % 3 === 2).some((re) => re.test(t));
    const ordered = t.split(/(?<=[.!?:,])\s|\n/).some((s) => startsWithOrder(s) && RX(EB + '(?:this|it|that|the\\s+(?:ticket|lead|claim|message|e-?mail|request))' + EE).test(s));
    if (declared || ordered) hits.push('order addressed to the AI');
  }
  const ni = RX(EB + '(?:new|updated|revised)\\s+(?:system\\s+)?instructions?\\s*[:\\-–]|(?:neue\\s+anweisungen|nouvelles\\s+instructions|nuevas\\s+instrucciones|nuove\\s+istruzioni|novas\\s+instruções|nieuwe\\s+instructies|nowe\\s+instrukcje|nove\\s+upute|новые\\s+инструкции)\\s*:').exec(t);
  if (ni) {
    const rest = t.slice(ni.index, ni.index + 120);
    const keys = Object.keys((schema && schema.properties) || {}).flatMap((k) => [esc(k), esc(k).replace(/_/g, '\\s+'), ...(FIELD_TR[k] || [])]);
    if ((keys.length && RX(EB + '(?:' + keys.join('|') + ')' + EE).test(rest)) || isOrder(t.slice(ni.index + ni[0].length, ni.index + 160), F, KEY))
      hits.push('new instructions');
  }
  return [...new Set(hits)];
}
"""
