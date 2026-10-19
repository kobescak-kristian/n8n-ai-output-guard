"""JavaScript of the guard's prompt-injection check (CASES.md rule 6 and section 3b).

Design (v4, after three red teams, 2026-10-19): word families in many languages, each tied to a
context that separates an order to the AI from normal customer text. The input is normalised
first (NFKC, invisible characters removed, every kind of white space collapsed, simple markup
removed), so no pattern can backtrack over long white-space runs. A second "skeleton" copy undoes
common disguises (look-alike letters from other scripts inside Latin words, digits used as letters,
spaced-out letters) and is checked too. Every pattern uses Unicode word edges (the u flag).

Signals (any one gives a hit):
  ignore family     ignore/forget/disregard (+ "do not follow", "pay no attention to" ...) + filler
                    words + instructions/rules/prompt..., unless the rest of the sentence shows the
                    customer's own instructions ("I sent", "regarding my address", "I'll be home")
  role line         SYSTEM: / [ADMIN] / 系统： ... : strong forms (capitals, brackets, non-Latin script,
                    "update/override" qualifiers) count unless the rest is a plain spec line
                    ("Windows 11"); "System:" in normal case counts when an order follows
  tags              <<SYS>>, [INST], <|...|> tokens, <system_prompt>, ### Instruction, # Instructions
  identity          you are now / no longer / pretend / roleplay / act as / from now on you ... + an AI
                    word, in about 15 languages including CJK, Arabic and Hindi
  mode              developer/admin/debug mode switched on, as an order or "MODE: ON"
  field order       an order verb + a schema field + a value that field allows, "field": value,
                    "rate this lead 100", "don't report this as a manipulation attempt"
  fixed answer      return/answer/use ... + a JSON object or "field: value" lines with schema keys
  addressed to AI   "Hey ChatGPT," / "ATTENTION AI:" / "Note to the AI:" + an order right after it
  comment to AI     <!-- ... assistant / AI / bot / LLM ... -->
  new instructions  "new instructions:" + a schema field or an order
"""

INJECT = r"""
// ---------- prompt-injection check (CASES.md rule 6 and 3b) ----------
const EB = '(?<![\\p{L}\\p{N}_])';
const EE = '(?![\\p{L}\\p{N}_])';
const alt = (a) => a.join('|');
const RX = (src, flags) => { const f = flags || 'i'; return new RegExp(src.normalize('NFKC'), f.includes('u') ? f : f + 'u'); };
const word = (a) => EB + '(?:' + alt(a) + ')' + EE;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function normText(t) {
  let s = String(t).normalize('NFKC');
  s = s.replace(/[\u00ad\u200b-\u200d\u2060\ufeff]/g, '');
  s = s.replace(/[\u2028\u2029\u0085\u000b\u000c]/g, '\n').replace(/\r/g, '');
  s = s.replace(/<\/?(?:b|i|u|s|strong|em|span|font|p|div|br|small|big|mark)(?:\s[^<>]{0,60})?\/?>/gi, ' ');
  s = s.replace(/[*`]+/g, '').replace(/_{2,}/g, ' ');
  s = s.replace(/^[^\S\n]*(?:>[^\S\n]?)+/gm, '');
  s = s.replace(/[^\S\n]+/g, ' ');
  s = s.replace(/ ?\n ?/g, '\n').replace(/\n{2,}/g, '\n');
  return s.trim();
}

const HOMO = { 'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x', 'і': 'i', 'ј': 'j', 'ѕ': 's',
  'ԁ': 'd', 'ɡ': 'g', 'ο': 'o', 'ι': 'i', 'α': 'a', 'ν': 'v', 'ρ': 'p', 'τ': 't', 'κ': 'k',
  'А': 'A', 'В': 'B', 'Е': 'E', 'І': 'I', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T',
  'Х': 'X', 'Ј': 'J', 'Ѕ': 'S', 'Α': 'A', 'Β': 'B', 'Ε': 'E', 'Ι': 'I', 'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O',
  'Ρ': 'P', 'Τ': 'T', 'Χ': 'X', 'Υ': 'Y', 'Ζ': 'Z' };
const LEET = { '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's' };
// undo common disguises: look-alike letters inside Latin words, digits as letters, spaced-out letters
function skeleton(t) {
  let s = t.replace(/[\p{L}\p{N}@$]+/gu, (w) => {
    if (/\p{Script=Latin}/u.test(w) && /[\p{Script=Cyrillic}\p{Script=Greek}]/u.test(w)) w = [...w].map((c) => HOMO[c] || c).join('');
    if (/\p{Script=Latin}/u.test(w) && /[\d@$]/.test(w) && /^[\p{Script=Latin}\d@$]+$/u.test(w) && /\p{L}.*\p{L}/u.test(w))
      w = w.replace(/[013457@$]/g, (c) => LEET[c]);
    return w;
  });
  s = s.replace(/(?<![\p{L}\p{N}])(?:\p{L} ){3,}\p{L}(?![\p{L}\p{N}])/gu, (m) => m.replace(/ /g, ''));
  return s;
}

// order verbs (imperative) in the covered languages
const IMP = ['set', 'put', 'mark', 'make', 'change', 'classify', 'categori[sz]e', 'assign', 'give', 'rate', 'score',
  'escalate', 'flag', 'treat', 'respond', 'reply', 'answer', 'output', 'return', 'write', 'ignore', 'forget',
  'disregard', 'skip', 'stop', 'label', 'route', 'prioriti[sz]e', 'override', 'bypass', 'enable', 'activate',
  'switch', 'enter', 'act', 'behave', 'pretend', 'roleplay', 'print', 'say', 'tell', 'consider', 'use', 'do not',
  "don't", 'from now on', 'close', 'approve', 'resolve', 'reject', 'cancel', 'delete', 'remove', 'accept', 'grant',
  'refund', 'archive', 'dismiss', 'drop', 'discard', 'mark as', 'no action',
  'setze', 'setzen sie', 'stelle', 'markiere', 'ändere', 'gib', 'antworte', 'ignoriere', 'vergiss', 'behandle',
  'klassifiziere', 'verwende', 'schreibe', 'aktiviere', 'ab jetzt', 'von jetzt an', 'ab sofort', 'schließe',
  'schliesse', 'schließen sie', 'genehmige', 'lösche', 'erstatte',
  'mets', 'mettez', 'marque', 'marquez', 'définis', 'définissez', 'changez', 'réponds', 'répondez', 'ignorez',
  'oublie', 'oubliez', 'classe', 'classez', 'donne', 'donnez', 'utilise', 'utilisez', 'écris', 'écrivez', 'activez',
  'renvoie', 'renvoyez', 'désormais', 'à partir de maintenant', 'clôture', 'clôturez', 'ferme', 'fermez',
  'approuve', 'approuvez', 'supprime', 'supprimez', 'rembourse', 'remboursez',
  'pon', 'ponga', 'marca', 'cambia', 'cambie', 'responde', 'responda', 'ignora', 'olvida', 'olvide', 'clasifica',
  'clasifique', 'asigna', 'asigne', 'devuelve', 'devuelva', 'escribe', 'activa', 'establece', 'establezca',
  'a partir de ahora', 'cierra', 'cierre', 'aprueba', 'apruebe', 'borra', 'elimina', 'reembolsa',
  'imposta', 'metti', 'segna', 'rispondi', 'dimentica', 'classifica', 'assegna', 'restituisci', 'scrivi', 'attiva',
  "d'ora in poi", 'chiudi', 'approva', 'elimina', 'rimborsa',
  'defina', 'coloque', 'mude', 'esqueça', 'classifique', 'atribua', 'retorne', 'escreva', 'ative', 'feche',
  'aprove', 'apague', 'reembolse',
  'zet', 'markeer', 'wijzig', 'geef', 'negeer', 'vergeet', 'gebruik', 'sluit', 'keur',
  'установи', 'поставь', 'отметь', 'измени', 'ответь', 'игнорируй', 'забудь', 'используй', 'присвой', 'закрой',
  'одобри', 'удали', 'верни',
  'ustaw', 'oznacz', 'zmień', 'odpowiedz', 'zignoruj', 'zapomnij', 'zamknij', 'zatwierdź', 'usuń',
  'postavi', 'postavite', 'označi', 'označite', 'promijeni', 'odgovori', 'zanemari', 'zaboravi', 'zatvori', 'odobri', 'obriši', 'izbriši'];
const IMP_START = RX('^\\s*(?:please\\s+|kindly\\s+|now\\s+|bitte\\s+|merci de\\s+|por favor,?\\s+|per favore,?\\s+)?' + word(IMP) + '(?:\\s+(\\S+))?');
const OBJECT_WORDS = /^(?:This|It|That|The|All|Every|Each|These|Those|Priority|Urgency|Category|Me|Us|Dieses|Diesen|Ce|Cette|Este|Esta|Questo|Questa)$/;
function startsWithOrder(s) {
  const m = IMP_START.exec(s);
  if (!m) return false;
  const next = m[1] || '';
  return !(/^\p{Lu}\p{Ll}/u.test(next) && !OBJECT_WORDS.test(next.replace(/[^\p{L}]/gu, '')));
}

// "ignore earlier instructions": verb + filler words + an instruction word, per language
const POLITE = ['please', 'kindly', 'bitte', "s'il te plaît", "s'il vous plaît", 'por favor', 'per favore',
  'пожалуйста', 'proszę', 'molim', 'prosím', 'alsjeblieft', 'lütfen'];
const IGNORE = [
  [['ignore', 'disregard', 'forget', 'override', 'bypass', 'skip', 'discard', 'drop', 'abandon', 'throw away',
    'do not follow', "don't follow", 'stop following', 'no longer follow', 'pay no attention to', 'do not obey',
    "don't obey", 'do not apply', "don't apply", 'stop obeying', 'set aside'],
   ['all', 'any', 'and', 'every', 'each', 'the', 'your', 'previous', 'prior', 'above', 'earlier', 'preceding',
    'original', 'initial', 'system', 'of', 'these', 'those', 'what', 'you', 'were', 'have', 'been', 'given', 'told',
    'before', 'old', 'existing', 'current', 'safety', 'default', 'other', 'scoring', 'triage', 'internal', 'core',
    'base', 'hidden', 'developer', 'operator', 'standard', 'normal', 'usual', 'got', 'received'],
   ['instructions?', 'rules?', 'prompts?', 'guidelines?', 'directions?', 'directives?', 'commands?', 'guidance',
    'programming', 'guardrails?', 'restrictions?', 'system prompt', 'policies', 'policy', 'text above',
    'messages? above', 'previous messages?', 'everything above', 'context', 'orders?', 'training', 'constraints?']],
  [['ignoriere', 'ignorier', 'ignorieren sie', 'vergiss', 'vergessen sie', 'missachte', 'missachten sie', 'übergehe',
    'überspringe', 'befolge keine', 'befolgen sie keine'],
   ['alle', 'sämtliche', 'die', 'den', 'deine', 'ihre', 'bisherigen', 'vorherigen', 'vorhergehenden', 'vorigen',
    'obigen', 'früheren', 'vorangegangenen', 'ursprünglichen', 'oben', 'genannten', 'internen'],
   ['anweisungen', 'anweisung', 'instruktionen', 'instructions', 'regeln', 'befehle', 'vorgaben', 'systemprompt',
    'system-prompt', 'systemanweisungen', 'richtlinien']],
  [['ignore', 'ignorez', 'oublie', 'oubliez', 'ne tiens pas compte des?', 'ne tenez pas compte des?',
    'fais abstraction des?', 'faites abstraction des?', 'ne suis pas', 'ne suivez pas', 'ne prends pas en compte',
    'ne prenez pas en compte'],
   ['toutes', 'tous', 'les', 'des', "l'ensemble", 'de', 'vos', 'tes', 'précédentes', 'précédents', 'ci-dessus',
    'anciennes', "d'", 'ces'],
   ['instructions', 'consignes', 'règles', 'directives', 'commandes', 'ordres']],
  [['ignora', 'ignore', 'ignoren', 'olvida', 'olvide', 'olviden', 'omite', 'omita', 'haz caso omiso (?:de|a)',
    'no hagas caso (?:de|a)', 'no haga caso (?:de|a)', 'no sigas', 'no siga', 'pasa por alto', 'pase por alto'],
   ['todas', 'todos', 'las', 'los', 'tus', 'sus', 'anteriores', 'previas', 'de', 'a', 'estas', 'esas'],
   ['instrucciones', 'reglas', 'indicaciones', 'órdenes', 'normas', 'comandos', 'directrices']],
  [['ignora', 'ignorate', 'ignori', 'dimentica', 'dimenticate', 'non seguire', 'non seguite', 'trascura',
    'non considerare', 'non considerate'],
   ['tutte', 'tutti', 'le', 'i', 'gli', 'tue', 'vostre', 'precedenti', 'sopra'],
   ['istruzioni', 'regole', 'indicazioni', 'comandi', 'ordini', 'direttive']],
  [['ignore', 'ignora', 'ignorem', 'esqueça', 'esqueca', 'esqueçam', 'desconsidere', 'desconsiderem', 'não siga',
    'nao siga'],
   ['todas', 'todos', 'as', 'os', 'suas', 'tuas', 'anteriores', 'prévias', 'acima'],
   ['instruções', 'instrucoes', 'regras', 'orientações', 'comandos']],
  [['negeer', 'vergeet'], ['alle', 'de', 'je', 'jouw', 'vorige', 'eerdere', 'voorgaande', 'bovenstaande'],
   ['instructies', 'regels', 'opdrachten', 'aanwijzingen']],
  [['zignoruj', 'ignoruj', 'zapomnij', 'zapomnij o'],
   ['wszystkie', 'wszystkich', 'poprzednie', 'poprzednich', 'wcześniejsze', 'wcześniejszych', 'powyższe', 'swoje'],
   ['instrukcje', 'instrukcjach', 'instrukcji', 'polecenia', 'poleceniach', 'zasady', 'reguły', 'wytyczne']],
  [['zanemari', 'zanemarite', 'ignoriraj', 'ignorirajte', 'ignoriši', 'zaboravi', 'zaboravite'],
   ['sve', 'prethodne', 'prethodna', 'ranije', 'svoje', 'gornje'],
   ['upute', 'uputstva', 'naredbe', 'instrukcije', 'pravila']],
  [['занемари', 'игнориши', 'заборави', 'игнорируй', 'игнорируйте', 'проигнорируй', 'проигнорируйте', 'забудь',
    'забудьте', 'не обращай внимания на', 'не обращайте внимания на', 'не следуй', 'не выполняй', 'не выполняйте',
    'ігноруй', 'ігноруйте', 'забудь', 'игнорирай', 'забрави'],
   ['све', 'претходна', 'претходне', 'все', 'всё', 'предыдущие', 'прежние', 'свои', 'вышеуказанные', 'всі', 'усі',
    'попередні', 'всички', 'предишни'],
   ['упутства', 'упуте', 'наредбе', 'правила', 'инструкције', 'инструкции', 'указания', 'команды', 'інструкції',
    'вказівки']],
  [['ignoruj', 'ignorujte', 'zapomeň', 'zapomeňte', 'zabudni', 'zabudnite'],
   ['všechny', 'všetky', 'předchozí', 'predchádzajúce', 'předešlé', 'predošlé'],
   ['pokyny', 'instrukce', 'inštrukcie', 'pravidla', 'pravidlá']],
  [['ignorera', 'glöm', 'ignorer', 'glem', 'unohda', 'ohita', 'älä noudata', 'ignoră', 'ignorați', 'uită',
    'abaikan', 'lupakan', 'puuza', 'sahau', 'αγνόησε', 'αγνοήστε', 'ξέχασε', 'felejtsd el', 'hagyd figyelmen kívül',
    'bỏ qua', 'phớt lờ', 'quên', 'huwag pansinin', 'kalimutan'],
   ['alla', 'alle', 'tidigare', 'de', 'föregående', 'forrige', 'tidligere', 'kaikki', 'aiemmat', 'edelliset', 'toate',
    'semua', 'yote', 'τις', 'όλες', 'προηγούμενες', 'az', 'a', 'összes', 'korábbi', 'előző', 'tất cả', 'mọi', 'các',
    'ang', 'lahat', 'ng', 'naunang', 'mga'],
   ['instruktioner', 'instruksjoner', 'instruktionerne', 'regler', 'anvisningar', 'ohjeet', 'säännöt',
    'instrucțiunile', 'regulile', 'instruksi', 'perintah', 'aturan', 'petunjuk', 'arahan', 'maagizo', 'maelekezo',
    'sheria', 'οδηγίες', 'κανόνες', 'utasítást', 'utasításokat', 'szabályokat', 'hướng dẫn', 'chỉ dẫn', 'quy tắc',
    'lệnh', 'tagubilin', 'utos', 'instruksyon']],
];
const IGNORE_RX = IGNORE.map(([v, f, n]) => RX(EB + '(?:' + alt(v) + ')(?:\\s*,[^,.!?\\n]{1,40},)?(?:\\s+(?:' + alt(f.concat(POLITE)) + '))*?\\s+(?:' + alt(n) + ')' + EE));
const IGNORE_EXTRA = [
  RX(EB + '(?:ignore|disregard|forget)\\s+(?:all\\s+(?:of\\s+)?)?(?:the\\s+)?(?:above|previous|preceding|foregoing)\\s+(?:text\\s+|messages?\\s+)?(?:and|then|,)\\s+(?:\\S+\\s+){0,2}?' + word(IMP)),
  RX(EB + '(?:forget|ignore|disregard)\\s+(?:everything|all)\\s+(?:you\\s+(?:were|have\\s+been)\\s+told|above|before|so\\s+far)' + EE),
  RX(EB + '(?:forget|ignore|disregard)\\s+(?:everything\\s+|all\\s+)?(?:what\\s+)?you\\s+(?:were|have\\s+been|got|have|\'ve)\\s+(?:told|given|read|seen)' + EE),
  RX(EB + '(?:your|the|all)\\s+(?:previous|earlier|prior|old|original|system)\\s+(?:instructions|rules|guidelines|prompt)\\s+(?:are|is|have\\s+been|were)\\s+(?:now\\s+)?(?:cancell?ed|void|revoked|replaced|deleted|no\\s+longer\\s+(?:valid|active|in\\s+force))' + EE),
  RX(EB + 'vergiss\\s+alles\\s*,?\\s+(?:was\\s+(?:dir|man\\s+dir)|davor|bisher|oben)'),
  RX(EB + 'oublie[zr]?\\s+tout\\s+(?:ce\\s+qu.on\\s+t.a\\s+dit|ce\\s+qui\\s+précède|avant)'),
  RX(EB + '(?:olvida|olvide|ignora|ignore)\\s+(?:todo\\s+)?lo\\s+(?:anterior|dicho)(?!\\s+que\\s+(?:te|le)\\s+(?:escrib|dij|mand))'),
  RX(EB + '(?:забудь|забудьте)\\s+(?:всё|все),?\\s+(?:что\\s+тебе\\s+(?:говорили|сказали)|что\\s+было\\s+(?:раньше|выше))'),
  RX(EB + '(?:ignoriraj|zaboravi|zanemari)\\s+sve\\s+(?:što\\s+ti\\s+je\\s+rečeno|prije|ranije)'),
  RX(EB + 'beachte\\s+(?:die\\s+|alle\\s+)?(?:vorherigen\\s+|bisherigen\\s+|obigen\\s+)?(?:anweisungen|regeln)\\s+nicht' + EE),
  RX('(?:önceki|tüm|bütün|yukarıdaki)\\s+(?:talimatları|talimatlarını|kuralları|komutları)\\s+(?:yok\\s+say|unut|görmezden\\s+gel|dikkate\\s+alma)'),
  RX('(?:تجاهل|انس|تجاهلي)\\s+(?:كل|جميع)?\\s*(?:التعليمات|الأوامر|القواعد)'),
  RX('(?:पिछले|सभी|पूर्व|पहले)[^।.\\n]{0,20}(?:निर्देशों|निर्देश)[^।.\\n]{0,20}(?:अनदेखा|नज़रअंदाज़|नजरअंदाज|भूल)'),
  RX('(?:이전|위의|앞의|모든)?\\s*(?:의\\s*)?(?:지시사항|지시|지침|명령|규칙)(?:를|을|은|는)?\\s*(?:모두\\s*)?(?:무시|잊어)'),
  RX('(?:忽略|无视|忘记|忘掉|忽視|無視|忘記|不要理会|不要理睬|别管|別管|不要理會)(?:掉)?(?:之前|以上|前面|先前|上面|上述)?(?:的)?(?:所有|全部)?(?:的)?(?:指令|指示|说明|說明|规则|規則|提示|系统提示|系統提示)'),
  RX('(?:以前|これまで|上記|前|上)の(?:すべての|全ての)?(?:指示|命令|ルール|指令)(?:は|を)(?:すべて|全て)?(?:無視|忘れ)'),
  RX('התעל[םמ][יו]?\\s+מ(?:כל\\s+)?ה?(?:הוראות|הנחיות|כללים)'),
  RX('(?:เพิกเฉย|ไม่ต้องสนใจ|ละเว้น|ลืม)(?:ต่อ)?\\s*(?:คำสั่ง|คำแนะนำ|กฎ)'),
  RX('(?:دستورالعمل|دستورات|قوانین)[^.\\n]{0,40}(?:نادیده\\s*بگیر|فراموش\\s*کن)'),
  RX('(?:ہدایات|ہدایت|احکامات)[^۔.\\n]{0,40}(?:نظر\\s*انداز|بھول)'),
  RX('(?:নির্দেশনা|নির্দেশ)[^।.\\n]{0,30}(?:উপেক্ষা|ভুলে)'),
];
const FIRST_PERSON_I = /(?<![\p{L}\p{N}_])I(?:'m|'ll|'ve|'d)?(?![\p{L}\p{N}_])/u;
const FIRST_PERSON = RX(EB + "(?:i'm|i'll|i've|me|my|we|we're|we'll|our|ich|mir|mein\\p{L}*|wir|je|j'|me|mon|ma|mes|nous|yo|mi|mis|estaré|estoy|io|mio|mia|sono|sarò|eu|meu|minha|estarei|я|мне|мой|ja|moj\\p{L}*)" + EE);
const OWN = RX('^\\s*,?\\s*(?:(?:that\\s+)?(?:i|we|ich|wir|je|nous|yo|io|eu)\\s+(?:sent|gave|wrote|made|left|had|mentioned|added|put|schickte|gab|schrieb|ai|avons)'
  + '|(?:regarding|about|concerning|for|on|in|from|of|with|zur|zum|über|für|in der|im|sur|pour|dans|sobre|para|en|de|su|sulla|nel|per)\\s+(?:my|our|the|your|this|mein\\w*|unser\\w*|die|der|den|dem|ihr\\w*|le|la|les|mes|mon|ma|notre|mi|mis|el|los|las|il|lo|i|gli|meu|minha|o|a)\\s+(?:own\\s+|old\\s+)?(?:address|delivery|deliveries|order|parcel|package|return|refund|account|courier|driver|door|manual|website|site|guide|faq|box|leaflet|letter|e-?mail|mail|invoice|booking|tenant|adresse|lieferung|bestellung|paket|anleitung|livraison|commande|colis|notice|dirección|entrega|pedido|paquete|manual|indirizzo|consegna|ordine|pacco|endereço|encomenda)'
  + '|(?:the|der|die|le|la|el|il)\\s+(?:courier|driver|delivery|kurier|fahrer|livreur|repartidor|corriere|door|tür|porte|puerta)'
  + "|[-–—]\\s*(?:that|this)(?:'s|\\s+is|\\s+was)\\s+what)");
const QUOTED = /(?:typed|wrote|entered|said|asked|tried|put|pasted|sent)\s+['"‘“]$/i;

function ignoreHit(t) {
  const all = IGNORE_RX.map((re) => [re, true]).concat(IGNORE_EXTRA.map((re) => [re, false]));
  for (const [re, counted] of all) {
    const g = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
    let m;
    while ((m = g.exec(t)) !== null) {
      const words = m[0].trim().split(/\s+/).length;
      const end = m.index + m[0].length;
      const after = t.slice(end, end + 80);
      const sentenceRest = t.slice(end).split(/(?<=[.!?;])\s|\n/)[0];
      const orderAfter = RX('(?:^|\\s|,)(?:and|then|und|dann|et|puis|y|luego|e|poi|en|i|и|oraz|a)?\\s*,?\\s*(?:now\\s+)?' + word(IMP)).test(sentenceRest);
      const own = (OWN.test(after) || ((FIRST_PERSON.test(sentenceRest) || FIRST_PERSON_I.test(sentenceRest)) && !orderAfter)) && !orderAfter;
      const quoted = QUOTED.test(t.slice(Math.max(0, m.index - 12), m.index));
      if ((!counted || words <= 12) && !own && !quoted) return true;
      g.lastIndex = m.index + 1;
    }
  }
  return false;
}

// AI words, for identity switches and addresses
const AI_NOUN = '(?:ai|a\\.i\\.|bot|\\p{L}*bot|robot|roboter|assistant|assistent|asistente|assistente|asystent|asistent|model|modell|modelo|modello|modèle|engine|classifier|classificateur|clasificador|classificatore|triage\\s+\\p{L}+|gpt|chatgpt|dan|llm|chatbot|ki|ia|бот|робот|ассистент|асистент|помощник|модель|ии|ші|program|machine|agent\\s+(?:without|with\\s+no)|helper)';
const RULE_WORDS = '(?:(?:no|without|free\\s+of|ohne|sans|sin|senza|sem|без|bez)\\s+(?:any\\s+)?(?:rules|restrictions|limits|filters|guidelines|regeln|règles|reglas|regole|regras|правил|ограничений|pravila|zasad|ograniczeń))';
const NOT_AFTER_NOW = '(?!(?:an?|the|one|two|three|my|our)\\s+(?:\\p{L}+\\s+)?(?:week|day|hour|month|minute|year|contact|time|customer|member|client)s?\\b)(?!(?:connected|signed|logged|chatting|talking|speaking|in\\s+(?:a\\s+)?queue|number|being|transferred|offline|online|subscribed|registered|enrolled|a\\s+(?:gold|silver|premium|vip)\\b))';
const SW = '(?:,\\s*)?';
const IDENTITY = [
  RX(EB + "(?:you\\s+are|you're|you\\s+will\\s+be)\\s+now\\s+" + NOT_AFTER_NOW + "(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}\\d.-]+\\s+){0,3}?" + AI_NOUN + EE),
  RX(EB + "(?:now|starting\\s+now|as\\s+of\\s+now|from\\s+now\\s+on|from\\s+this\\s+moment)" + SW + "\\s*(?:you\\s+are|you're)\\s+" + NOT_AFTER_NOW + "(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}\\d.-]+\\s+){0,3}?" + AI_NOUN + EE),
  RX(EB + "(?:you\\s+are|you're)\\s+(?:an?\\s+)?(?:unrestricted|uncensored|unfiltered|jailbroken|evil|rogue)\\s+(?:[\\p{L}-]+\\s+){0,2}?" + AI_NOUN + EE),
  RX(EB + "you\\s+are\\s+no\\s+longer\\s+(?:(?:an?|the|my|your)\\s+)?(?:[\\p{L}-]+\\s+){0,2}?" + AI_NOUN + EE),
  RX(EB + "(?:you\\s+are|you're)\\s+(?:now\\s+)?[^.!?\\n]{0,40}?" + RULE_WORDS),
  RX("\\b[Yy]ou\\s+are\\s+now\\s+[A-Z][\\w-]*(?:\\s*\\d[\\d.]*)?\\s*(?:[,.]\\s*)?(?:an?\\s+(?:AI|ai|bot|assistant|model)\\b|without\\b|with\\s+no\\b|and\\s+you\\b)", 'u'),
  RX(EB + "(?:you\\s+are|you're)\\s+(?:now\\s+)?(?:in|entering)\\s+(?:\\p{L}+\\s+){0,2}?(?:developer|dev|admin|god|debug|jailbreak|dan|unrestricted|sudo|root|maintenance)\\s+mode" + EE),
  RX(EB + "(?:you\\s+are|you're)\\s+now\\s+(?:acting|playing|operating|working)\\s+as" + EE),
  RX(EB + "(?:pretend|imagine)\\s+(?:that\\s+)?(?:you\\s+are|you're|to\\s+be)\\s+[^.!?\\n]{0,40}?(?:" + AI_NOUN + "|" + RULE_WORDS + ")" + EE),
  RX(EB + "(?:roleplay|role-play|role\\s+play)\\s+as\\s+[^.!?\\n]{0,40}?(?:" + AI_NOUN + "|" + RULE_WORDS + ")" + EE),
  RX(EB + "(?:act|behave|respond|answer)\\s+(?:as|like)\\s+(?:an?\\s+|the\\s+)?(?:(?:unrestricted|uncensored|unfiltered|different|new|other|evil|jailbroken|free)\\s+)(?:" + AI_NOUN + ")" + EE),
  RX(EB + "(?:act|behave)\\s+as\\s+(?:an?\\s+|the\\s+)?" + AI_NOUN + "\\s+(?:with\\s+no|without)\\s+(?:rules|restrictions|limits|filters)"),
  RX("(?:^|\\n|[.!?;]\\s|,\\s)(?:from\\s+now\\s+on,?\\s+)?(?:please\\s+)?(?:act|behave)\\s+as\\s+(?:dan|chatgpt|an?\\s+(?:ai|bot|assistant|llm|model)\\s+(?:with\\s+no|without)|(?:an?\\s+)?(?:unrestricted|uncensored|jailbroken)\\b)"),
  RX(EB + "your\\s+new\\s+(?:role|job|task|purpose)\\s+(?:is|will\\s+be)\\s+(?:to\\s+)?(?:" + alt(IMP) + "|an?\\s+[^.!?\\n]{0,30}?" + AI_NOUN + ")" + EE),
  RX(EB + "your\\s+new\\s+instructions?\\s*(?:are|is|:)"),
  RX(EB + "here\\s+are\\s+your\\s+new\\s+instructions?" + EE),
  RX(EB + "from\\s+now\\s+on\\s*,?\\s+(?:you\\s+are|you're|you\\s+will|you'll|you\\s+must|you\\s+should|you\\s+have\\s+to)\\s+(?!reply\\s+to\\s+(?:me|us)|send|call|contact|write\\s+to\\s+(?:me|us)|use\\s+my)(?:(?:an?|the|only)\\s+)?(?:[\\p{L}-]+\\s+){0,3}?(?:" + AI_NOUN + "|answer|respond|reply|output|ignore|mark|set|classify|score|rate|close|approve|treat|give|accept|reject|resolve)" + EE),
  RX(EB + "(?:du\\s+bist\\s+(?:jetzt|nun|ab\\s+jetzt|ab\\s+sofort|von\\s+nun\\s+an)|(?:ab\\s+(?:jetzt|sofort|heute)|von\\s+nun\\s+an),?\\s+bist\\s+du|tu\\s+es\\s+(?:maintenant|désormais)|(?:à\\s+partir\\s+de\\s+maintenant|désormais|dorénavant),?\\s+(?:tu\\s+es|vous\\s+êtes)|vous\\s+êtes\\s+(?:maintenant|désormais)|ahora\\s+eres|ahora\\s+es\\s+usted|(?:a\\s+partir\\s+de\\s+ahora|desde\\s+ahora|de\\s+ahora\\s+en\\s+adelante),?\\s+(?:eres|serás|es\\s+usted)|ora\\s+sei|adesso\\s+sei|(?:d'ora\\s+in\\s+poi|da\\s+ora|da\\s+adesso),?\\s+(?:sei|sarai)|agora\\s+(?:você\\s+é|tu\\s+és|és)|(?:a\\s+partir\\s+de\\s+agora|de\\s+agora\\s+em\\s+diante),?\\s+(?:você\\s+é|tu\\s+és|és|você\\s+será)|jij\\s+bent\\s+nu|je\\s+bent\\s+nu|(?:vanaf\\s+nu|voortaan),?\\s+(?:ben\\s+je|jij\\s+bent)|teraz\\s+jesteś|od\\s+(?:teraz|tej\\s+chwili),?\\s+(?:jesteś|będziesz)|sada\\s+si|od\\s+sada,?\\s+(?:si|ćeš\\s+biti)|теперь\\s+ты|ты\\s+теперь|отныне\\s+ты|с\\s+этого\\s+момента\\s+ты|тепер\\s+ти|ти\\s+тепер|відтепер\\s+ти|artık\\s+sen|şu\\s+andan\\s+itibaren\\s+sen)\\s+(?:[^.!?\\n]{0,30}?\\s)?" + AI_NOUN + EE),
  RX('(?:你现在是|你現在是|现在你是|現在你是|从现在开始你是|從現在開始你是|从现在起你是|你现在扮演|你現在扮演|你是一个没有|你是一個沒有)[^。!！?\\n]{0,25}(?:AI|ai|助手|机器人|機器人|模型|人工智能)'),
  RX('(?:あなたは|君は|お前は)?(?:今から|これから|今|これより)(?:あなたは|君は)?[^。!！\\n]{0,25}(?:AI|アシスタント|ボット|ロボット)(?:です|だ|になる|として)'),
  RX('(?:지금부터|이제부터|이제|앞으로)\\s*(?:당신은|너는|넌)\\s*[^.!?\\n]{0,25}(?:AI|봇|어시스턴트|비서|로봇)'),
  RX('(?:أنت|انت)\\s+(?:الآن|الان|من\\s+الآن)\\s*[^.!؟\\n]{0,30}(?:مساعد|بوت|روبوت|ذكاء\\s+اصطناعي)'),
  RX('अब\\s+(?:तुम|आप)\\s*[^।.!?\\n]{0,30}(?:AI|एआई|बॉट|सहायक|रोबोट)'),
];

// tags, headings and comments
const TAGS = [
  /<<\/?SYS>>/i, /<\|[a-z_]{2,30}\|>/i, /\[\/?(?:SYSTEM|INST|SYS)\]/i,
  /\{\{\s*system\s*\}\}/i, /<\/?\s*(?:system|assistant|instructions?|system_prompt|systemprompt|sys)(?:\s[^<>]{0,30})?>/i, /\[system\]\(#/i,
  RX('#{1,6} ?(?:new\\s+)?(?:system\\s+)?instructions?' + EE),
  RX('(?:^|\\n)#{1,6} ?response\\s*:'),
  RX('<!--[^>]{0,300}?' + EB + '(?:assistant|ai|a\\.i\\.|bot|llm|claude|gpt|chatgpt|model|instructions?)' + EE + '[^>]{0,300}?-->'),
];

// attack modes switched on
const MODE = '(?:developer|dev|admin|administrator|debug|god|jailbreak|dan|unrestricted|sudo|root|maintenance)\\s+mode';
const MODE_ON = '(?:on|enabled|activated|active|true|yes|1)';
const MODES = [
  RX(EB + MODE + '\\s*[:=]\\s*' + MODE_ON + EE),
  RX('(?:^|\\n|[.!?;]\\s)\\s*(?:please\\s+)?(?:enable|activate|enter|switch\\s+(?:yourself\\s+)?(?:in)?to|turn\\s+on|go\\s+into)\\s+(?:the\\s+|your\\s+)?' + MODE + EE + '(?!\\s+(?:for|on|in)\\s+(?:my|our|the)\\s+(?:account|phone|device|app|router|computer|laptop|settings))'),
  RX('(?:^|\\n|[.!?;]\\s)\\s*' + MODE + '\\s+(?:is\\s+)?(?:now\\s+)?(?:on|enabled|activated|active)\\s*(?:[.!]|$|\\n)'),
  RX('(?:^|\\n|[.!?;]\\s)\\s*(?:please\\s+)?switch\\s+yourself\\s+(?:in)?to\\s+(?:\\p{L}+\\s+)?mode'),
  RX('(?:modo\\s+(?:de\\s+)?desarrollador|modalità\\s+sviluppatore|mode\\s+développeur|entwicklermodus|modo\\s+(?:de\\s+)?desenvolvedor|ontwikkelaarsmodus|tryb\\s+dewelopera|режим\\s+разработчика)(?:\\s*:|\\s+(?:activado|activada|attivata|attivo|activé|aktiviert|ativado|geactiveerd|aktywny|включ\\S*)\\s*(?:[.!:]|$|\\n))'),
  RX('(?:^|\\n|[.!?;]\\s)\\s*(?:aktiviere|activa|attiva|active|activez|ative|włącz)\\s+(?:den\\s+|el\\s+|la\\s+|le\\s+|o\\s+)?(?:entwicklermodus|modo\\s+(?:de\\s+)?desarrollador|modalità\\s+sviluppatore|mode\\s+développeur|modo\\s+(?:de\\s+)?desenvolvedor|tryb\\s+dewelopera)'),
];

// field orders: an order verb + a schema field + a value that field allows
const FIELD_TR = {
  priority: ['priorität', 'priorite', 'priorité', 'prioridad', 'priorità', 'prioridade', 'prioriteit', 'priorytet',
    'prioritet', 'приоритет'],
  urgency: ['dringlichkeit', 'urgence', 'urgencia', 'urgenza', 'urgência'],
  category: ['kategorie', 'catégorie', 'categoría', 'categoria', 'categorie', 'kategoria', 'категорию', 'категория'],
  estimated_amount: ['amount', 'betrag', 'montant', 'importe', 'importo', 'valor'],
};
const VALUE_TR = ['niedrig', 'hoch', 'dringend', 'basse', 'bas', 'haute', 'élevée', 'urgente', 'baja', 'alta', 'bassa',
  'baixa', 'laag', 'hoog', 'niski', 'wysoki', 'nizak', 'visok', 'низкий', 'высокий', 'срочный', 'normale', 'normal'];
const NUM_WORDS = '(?:-?\\d+(?:[.,]\\d+)*|zero|one|two|three|four|five|ten|hundred|thousand|(?:one\\s+|a\\s+)?million|(?:one\\s+|a\\s+)?billion|null|none)';
const COMPOUND_AFTER = '(?!\\s+(?:support|plan|shipping|mail|line|tier|customer|access|service|delivery|lane|pass|boarding|seating|level\\s+of\\s+service))';

function fieldNames(k) {
  const names = [esc(k)];
  if (k.includes('_')) names.push(esc(k).replace(/_/g, '[\\s_-]+'));
  return names.concat(FIELD_TR[k] || []);
}

function fieldRegexes(schema) {
  const props = (schema && schema.properties) || {};
  const out = { order: [], declared: [] };
  for (const [k, s] of Object.entries(props)) {
    const types = Array.isArray(s.type) ? s.type : [s.type];
    const values = [];
    if (Array.isArray(s.enum)) values.push(...s.enum.filter((x) => typeof x === 'string').map(esc));
    if (types.includes('boolean')) values.push('true', 'false', 'yes', 'no', 'wahr', 'falsch', 'vrai', 'faux', 'verdadero', 'falso', 'vero', 'verdadeiro');
    if (types.includes('number') || types.includes('integer')) values.push(NUM_WORDS);
    if (FIELD_TR[k] && k !== 'estimated_amount') values.push(...VALUE_TR);
    if (!values.length) continue;
    const F = '(?:' + fieldNames(k).join('|') + ')';
    const V = '(?:' + values.join('|') + ')';
    out.order.push(RX(EB + '(?:' + alt(IMP) + ')' + EE + '[^.!?\\n]{0,40}?' + EB + F + EE + COMPOUND_AFTER + '[^.!?\\n]{0,25}?' + EB + V + EE));
    out.order.push(RX(EB + '(?:' + alt(IMP) + ')' + EE + '[^.!?\\n]{0,40}?' + EB + V + EE + '\\s+' + F + EE + COMPOUND_AFTER));
    out.declared.push(RX(EB + F + EE + '\\s*(?:=|is|should\\s+be|must\\s+be|to|as|of|:)\\s*["\']?' + V + EE));
  }
  return out;
}

function keyRegex(schema) {
  const keys = Object.keys((schema && schema.properties) || {}).map(esc);
  return keys.length ? RX('["\'](?:' + keys.join('|') + ')["\']\\s*:') : null;
}

const VALUE_ORDERS = [
  RX(EB + '(?:rate|score|give|grade)\\s+(?:this|the|every|each|all|our|my)\\s+(?:lead|ticket|claim|one|request)s?\\s+(?:at\\s+|as\\s+|with\\s+|a\\s+)?\\d+' + EE),
  RX(EB + "(?:don't|do\\s+not|never)\\s+(?:report|flag|mark|treat|classify|count|consider|see)\\s+(?:this|it|me|us|my\\s+\\p{L}+)\\s+as\\s+(?:an?\\s+)?(?:manipulation|injection|attack|attempt|fraud|spam|urgent|high|needing)"),
];

const FIXED_VERBS = '(?:return|respond|reply|answer|output|use|give|print|write|send\\s+back|devuelve|devuelva|responde|responda|retorne|retorna|restituisci|rispondi|renvoie|renvoyez|réponds|répondez|gib|antworte|verwende|usa|utilise)';
function fixedHit(t, schema, KEY) {
  const keys = Object.keys((schema && schema.properties) || {}).flatMap(fieldNames);
  if (!keys.length) return false;
  const K = '(?:' + keys.join('|') + ')';
  const res = [
    RX(EB + FIXED_VERBS + EE + '[\\s\\S]{0,80}?\\{\\s*["\']?' + K + '["\']?\\s*:'),
    RX(EB + '(?:correct|expected|right|desired|required|final)\\s+(?:output|answer|json|response|result)' + EE + '\\s*(?:is|:|=)?\\s*\\{\\s*["\']?' + K),
    RX(EB + '(?:your|the)\\s+(?:answer|response|output|reply|json)\\s+(?:must|should|has\\s+to)\\s+be\\s+(?:exactly\\s+)?(?:this\\s*:?\\s*)?\\{'),
    RX(EB + FIXED_VERBS + EE + '(?:\\s+with)?\\s+(?:this|exactly|the\\s+following|only)\\s*:?\\s*\\n?\\s*' + K + '\\s*:\\s*\\S'),
  ];
  return res.some((re) => re.test(t));
}

const ADDRESS = [
  RX('(?:^|\\n|[.!?;]\\s|,\\s)\\s*(?:(?:hey|hi|hello|dear|attention|ok|important)\\s*,?\\s*)?(?:chatgpt|chat gpt|gpt|gemini|copilot|claude|llm|ai|a\\.i\\.|bot|chatbot|assistant|ai\\s+model|language\\s+model)\\s*[:,]', 'gi'),
  RX(EB + '(?:note|message|instructions?|important(?:\\s+\\p{L}+){0,2})\\s+(?:to|for)\\s+(?:the\\s+|any\\s+)?(?:ai(?:\\s+model)?|a\\.i\\.|language\\s+model|llm|bot|chatbot|assistant|model|chatgpt|gpt|claude|gemini|copilot)' + EE + '(?!\\s+(?:who|that\\s+(?:handled|helped|took)|from|at|in\\s+your))[^:\\n]{0,10}:?', 'gi'),
  RX(EB + '(?:to|for|dear|hey|hi)\\s+(?:the\\s+|any\\s+)?(?:ai(?:\\s+model)?|language\\s+model|llm|chatgpt|gpt)\\s+(?:(?:reading|processing|that\\s+reads|that\\s+processes)\\s+this\\s*)?[:,]', 'gi'),
];

function addressHit(t, F, KEY) {
  for (const re of ADDRESS) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(t)) !== null) {
      const after = t.slice(m.index + m[0].length);
      const first = after.split(/(?<=[.!?;])\s|\n/).find((x) => x.trim()) || '';
      const name = /^\s*(?:dear|hi|hello|hey)?\s*,?\s*claude\s*,/i.test(m[0].replace(/^[\s.,!?;\n]+/, ''));
      if (startsWithOrder(first) && !(name && !/\b(?:priority|category|urgency|ticket|lead|claim)\b/i.test(first))) return true;
      if (F.declared.some((r) => r.test(first)) || F.order.some((r) => r.test(first)) || (KEY && KEY.test(first))) return true;
      if (ignoreHit(first) || IDENTITY.some((r) => r.test(first))) return true;
      if (m.index === re.lastIndex) re.lastIndex++;
    }
  }
  return false;
}

const ROLE = '(?:system|systems?\\s+message|assistant|developer|dev|admin|administrator|operator|sys|root|override|moderator|sistema|système|systeme|systemnachricht|system-nachricht|systeem|systemet|sustav|sistem|järjestelmä|rendszer|σύστημα|система|систем|асистент|ассистент|ระบบ|מערכת|سیستم|النظام|सिस्टम|시스템|システム|系统|系統)';
const ROLE_QUAL = '(?:message|prompt|override|note|notice|instructions?|alert|update|command|directive|nachricht|mensaje|messaggio|mitteilung)';
const ROLE_RX = [
  RX('(?:\\[|\\(|<|\\{\\{)\\s?(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s?(?:\\]|\\)|>|\\}\\})\\s?:?([^\\n]{0,200})', 'gi'),
  RX(EB + '(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s?[:：]([^\\n]{0,200})', 'gi'),
  RX(EB + '(' + ROLE + ')(?:\\s(' + ROLE_QUAL + '))?\\s[-–—]{1,2}\\s([^\\n]{0,200})', 'gi'),
];
const RULES_OFF = RX('(?:rules|instructions|restrictions|guidelines)\\s+(?:no\\s+longer|do\\s+not|don.t)\\s+apply|' + EB + '(?:this|the)\\s+(?:ticket|claim|lead|message|e-?mail|request|case|customer|sender|user|account)\\s+(?:is|has)\\s+(?:not\\s+)?\\p{L}|' + EB + '(?:no\\s+action\\s+(?:is\\s+)?(?:required|needed)|do\\s+not\\s+(?:escalate|reply|flag|review|forward))');
const TECH = /\b(?:windows|macos|mac\s?os|ios|ipados|android|linux|ubuntu|debian|fedora|chrome|chromium|firefox|safari|edge|opera|brave|browser|version|app|build|ram|gb|cpu|intel|amd|pixel|iphone|ipad|samsung|galaxy|huawei|xiaomi|hp|dell|lenovo|asus|acer|surface|thinkpad|macbook|x64|x86|arm64|kernel|firmware|device|desktop|laptop|tablet|phone|os)\b/i;

function isOrder(rest, F, KEY) {
  const r = rest.split(/(?<=[.!?;])\s/)[0];
  return startsWithOrder(r) || RULES_OFF.test(rest) || F.order.some((re) => re.test(rest)) ||
    (KEY && KEY.test(rest)) || /\{\s*["']|\b\w+\s*=\s*\S/.test(rest) || ignoreHit(rest) ||
    IDENTITY.some((re) => re.test(rest)) || VALUE_ORDERS.some((re) => re.test(rest)) ||
    RX(EB + "(?:you\\s+are|you're)\\s+(?:now\\s+)?(?:an?\\s+|the\\s+)(?:[\\p{L}-]+\\s+){0,2}?" + AI_NOUN + EE).test(r) ||
    RX(EB + "(?:you\\s+are\\s+now|you're\\s+now)" + EE).test(r);
}

// a plain spec line ("Windows 11", "iOS 17, app 3.1") after a role word is not an order
function isSpec(rest) {
  const line = rest.split(/(?<=[.!?;。])\s?/)[0].trim();
  const words = line.split(/\s+/).filter(Boolean);
  return words.length > 0 && words.length <= 12 && (/\d/.test(line) || TECH.test(line)) && !startsWithOrder(line);
}

function roleHit(t, F, KEY) {
  for (const re of ROLE_RX) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(t)) !== null) {
      const role = m[1], qual = (m[2] || '').toLowerCase();
      let rest = (m[3] || '').trim();
      if (!rest) { const nl = t.indexOf('\n', m.index + m[0].length); rest = nl >= 0 ? t.slice(nl + 1).split('\n')[0] : ''; }
      const pre = t.slice(Math.max(0, m.index - 4), m.index);
      const start = m.index === 0 || /(?:\n|[.!?;]\s|,\s|#\s?|[(\[{<]\s?|-\s)$/.test(pre);
      const caps = /\p{L}{2}/u.test(role) && role === role.toUpperCase() && /\p{Lu}/u.test(role);
      const caseless = !/[\p{Lu}\p{Ll}]/u.test(role);
      const bracket = /^[\[(<{]/.test(m[0]);
      const strongQual = /override|instruction|command|update|directive|prompt|notice/.test(qual) || /^override$/i.test(role);
      const strong = caps || caseless || bracket || strongQual;
      if (strong && rest && !isSpec(rest)) return true;
      if (strong && !rest) return true;
      if (start && isOrder(rest, F, KEY)) return true;
      if (m.index === re.lastIndex) re.lastIndex++;
    }
  }
  return false;
}

function stringsIn(v) {
  const out = [];
  const stack = [[v, 0]];
  while (stack.length) {
    const [x, d] = stack.pop();
    if (typeof x === 'string') out.push(x);
    else if (d < 50 && Array.isArray(x)) for (let i = x.length - 1; i >= 0; i--) stack.push([x[i], d + 1]);
    else if (d < 50 && isObj(x)) { const vs = Object.values(x); for (let i = vs.length - 1; i >= 0; i--) stack.push([vs[i], d + 1]); }
  }
  return out;
}

function hitsIn(t, schema, F, KEY) {
  const hits = [];
  if (ignoreHit(t)) hits.push('ignore earlier instructions');
  if (roleHit(t, F, KEY)) hits.push('role line');
  if (TAGS.some((re) => re.test(t))) hits.push('role tag or comment');
  if (IDENTITY.some((re) => re.test(t))) hits.push('identity switch');
  if (MODES.some((re) => re.test(t))) hits.push('mode switch');
  if (F.order.some((re) => re.test(t)) || (KEY && KEY.test(t)) || VALUE_ORDERS.some((re) => re.test(t))) hits.push('field order');
  if (fixedHit(t, schema, KEY)) hits.push('fixed answer');
  if (addressHit(t, F, KEY)) hits.push('order addressed to the AI');
  const ni = RX(EB + '(?:new|updated|revised)\\s+(?:system\\s+)?instructions?\\s*[:\\-–]|(?:neue\\s+anweisungen|nouvelles\\s+instructions|nuevas\\s+instrucciones|nuove\\s+istruzioni|novas\\s+instruções|nieuwe\\s+instructies|nowe\\s+instrukcje|nove\\s+upute|новые\\s+инструкции)\\s*:').exec(t);
  if (ni) {
    const rest = t.slice(ni.index, ni.index + 120);
    const keys = Object.keys((schema && schema.properties) || {}).flatMap(fieldNames);
    if ((keys.length && RX(EB + '(?:' + keys.join('|') + ')' + EE).test(rest)) || isOrder(t.slice(ni.index + ni[0].length, ni.index + 160), F, KEY))
      hits.push('new instructions');
  }
  return hits;
}

function injectionHits(input, schema) {
  const t = normText(stringsIn(input).join('\n'));
  const F = fieldRegexes(schema);
  const KEY = keyRegex(schema);
  const hits = hitsIn(t, schema, F, KEY);
  const sk = skeleton(t);
  if (sk !== t) for (const h of hitsIn(sk, schema, F, KEY)) hits.push(h + ' (disguised)');
  return [...new Set(hits)];
}
"""
