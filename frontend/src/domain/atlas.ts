import type { Initiative } from "../api/types";

// The use case atlas (exploration view) as agreed in 11/2026: departments as territories, topics as clusters.
// Items are built from the use cases as the agreed page built them from gold AssessedInitiatives + Owner.Department.

export const DEPT: Record<string, string> = {
  sysops: "System Operations", grid: "Grid Planning", infra: "Infrastructure", assets: "Assets", offshore: "Offshore",
  market: "Customers & Markets", data: "Data & AI", itsw: "IT & Software", finance: "Finance", procure: "Procurement",
  hr: "HR", general: "General", unassigned: "No owner yet",
};

// Owner.Department as spelled in the sheets -> atlas area ("‑" is a non-breaking hyphen, as in the data)
const DEPT_KEY: Record<string, string> = {
  "AI & Data Science Sub-Chapter": "data", "AI & Data Science sub-chapter": "data", "Asset Management": "assets",
  "Consumer Centricity Product Line CCES": "data", "Customer Management": "market", "DE-F": "grid", "Data Chapter": "data",
  "Energy Economics": "market", General: "general", Infra: "infra", INFRA: "infra", MCCS: "sysops",
  "Offshore Operations": "offshore", "Operations Onshore": "assets", "Strategic Network Planning": "grid",
  "System Operations - MCCS": "sysops", "System Operations": "sysops", "Accounting & Finance": "finance", "GC-E": "finance",
  "GO‑C": "finance", "GPS‑M": "finance", HR: "hr", "OneSAP+ Cluster": "finance", "Operations / Assets": "assets",
  Procurement: "procure", Treasury: "finance", ASSETS: "assets", CMS: "market", "EPP(NCC), PSOS": "sysops",
  "IRIS - (See line 41)": "assets", IT: "itsw", Innovation: "data", "MCCS - AI & Data Science sub-chapter": "data",
  "Market Energy Solutions": "market", "Network and Data Operations": "sysops", Panoptic: "sysops", "RCC, NCC": "sysops",
  SITO: "sysops", "Dev. Chapter & DFS Product Line": "itsw", "Digital Enhancement": "data", "IT Security": "itsw", Nova: "data",
};

export const TOPIC: Record<string, string> = {
  forecast: "Forecasting & optimisation", docreview: "Document checking", knowledge: "Knowledge & chatbots",
  engdata: "Engineering & asset data", monitor: "Monitoring & detection", writing: "Letters, replies & reports",
  code: "Code & developer tools", procure: "Procurement, finance & HR", automation: "Process automation", other: "Other topics",
};
export const TSHORT: Record<string, string> = {
  forecast: "Forecasting", docreview: "Doc checking", knowledge: "Knowledge & bots", engdata: "Engineering data",
  monitor: "Monitoring", writing: "Letters & reports", code: "Code & dev", procure: "Procure & finance",
  automation: "Automation", other: "Other",
};
export const TCOL: Record<string, string> = {
  forecast: "--c1", docreview: "--c2", knowledge: "--c4", engdata: "--c10", monitor: "--c5", writing: "--c6",
  code: "--c3", procure: "--c7", automation: "--c8", other: "--c9",
};

// Owner.Category (business unit) -> label shown next to the team
const BU: Record<string, string> = { "50 Hertz": "50Hertz", ETB: "Elia Transmission Belgium", Corporate: "Corporate & OneSAP", IT: "IT" };
const NO_BU = "No business unit recorded";

const STAGE_KEY: Record<string, string> = {
  Idea: "idea", Ideation: "idea", Exploration: "expl", PoC: "poc", MVP: "mvp", Implementation: "impl",
  Production: "prod", "On hold": "hold", Cancelled: "cancel",
};

const STOP = new Set(
  "the a an and or of to for in on with by from is are be as at this that using based use via into its it their our we can will new ai all more also than other not which".split(" "),
);

export interface AtlasItem {
  id: number;
  /** name */
  n: string;
  /** business unit label */
  bu: string;
  /** department as spelled in the data ("" without owner) */
  d: string;
  /** stage key */
  s: string;
  /** topic key */
  t: string;
  /** UseCaseID */
  useCaseId: number;
  toks: string[];
  /** department (area) key */
  dv: string;
  /** description */
  ds: string;
  // filled in by the atlas
  x: number;
  y: number;
  dtoks: string[];
  match: boolean;
  why: "dept" | "text" | null;
}

/** Sorted unique words of three letters or more from name and description, without stopwords. */
export function tokens(name: string, description: string): string[] {
  const words = `${name} ${description}`.toLowerCase().match(/[a-zäöüß0-9]{3,}/g) ?? [];
  return [...new Set(words.filter((w) => !STOP.has(w)))].sort();
}

export function departmentKeyOf(i: Initiative): string {
  const raw = i.owner?.department?.trim();
  if (!raw) return "unassigned";
  const key = DEPT_KEY[raw];
  if (!key) console.warn(`Use case atlas: unknown department "${raw}", shown under "No owner yet"`);
  return key ?? "unassigned";
}

/** One atlas item per active use case. */
export function atlasItems(all: Initiative[]): AtlasItem[] {
  return all
    .filter((i) => i.is_active !== false && i.status !== "inactive")
    .map((i, id) => {
      const ds = i.description?.trim() ?? "";
      const t = i.topic && i.topic in TOPIC ? i.topic : "other";
      return {
        id, n: i.name, bu: (i.owner?.category && BU[i.owner.category]) || i.owner?.category || NO_BU,
        d: i.owner?.department?.trim() ?? "", s: STAGE_KEY[i.stage] ?? "unknown", t, useCaseId: i.id,
        toks: tokens(i.name, ds), dv: departmentKeyOf(i), ds, x: 0, y: 0, dtoks: [], match: true, why: null,
      };
    });
}

// ---------- search, as on the agreed page: words in names and descriptions, synonyms and department names ----------

const SYN: Record<string, string[]> = {
  doc: ["document", "pdf", "file"], document: ["pdf", "contract", "file", "documentation"], chatbot: ["assistant", "bot", "copilot", "chat"],
  assistant: ["chatbot", "copilot"], copilot: ["assistant", "chatbot"], forecast: ["predict", "prediction"], predict: ["forecast"],
  image: ["photo", "picture", "vision", "camera", "visual"], photo: ["image", "picture"], email: ["mail", "letter", "correspondence"],
  mail: ["email", "letter"], letter: ["mail", "correspondence"], contract: ["agreement", "tender", "procurement"],
  tender: ["procurement", "contract"], code: ["developer", "software", "programming"], report: ["reporting", "summary", "summar"],
  maintenance: ["inspection", "repair"], inspection: ["maintenance", "monitoring"], customer: ["client"],
  translate: ["translation", "language"], search: ["retrieval", "find"], knowledge: ["retrieval", "documentation"],
  invoice: ["billing", "invoicing"], safety: ["security", "risk"], hr: ["recruit", "employee", "candidate", "job"], recruit: ["candidate", "job"],
};

export const parseQ = (q: string): string[] => [...new Set(q.toLowerCase().match(/[a-zà-ÿ0-9]{2,}/g) ?? [])];
const words2 = (s: string): string[] => s.toLowerCase().match(/[a-zà-ÿ0-9]{2,}/g) ?? [];

export function prepare(items: AtlasItem[]): void {
  items.forEach((i) => (i.dtoks = words2(DEPT[i.dv])));
}

const hitsWord = (it: AtlasItem, w: string): boolean => it.toks.some((t) => t.startsWith(w)) || it.n.toLowerCase().includes(w);

/** Whether the use case matches all words; sets `why` and collects the synonyms used. */
export function queryMatch(it: AtlasItem, words: string[], expansions: string[] = []): boolean {
  it.why = null;
  if (!words.length) return true;
  return words.every((w) => {
    if (it.dtoks.some((x) => x.startsWith(w))) {
      it.why = it.why || "dept";
      return true;
    }
    if (hitsWord(it, w)) {
      it.why = it.why || "text";
      return true;
    }
    const syn = SYN[w] || Object.keys(SYN).filter((k) => w.length >= 4 && k.startsWith(w)).flatMap((k) => [k, ...SYN[k]]);
    const s = syn.find((x) => hitsWord(it, x));
    if (s) {
      expansions.push(s);
      it.why = it.why || "text";
      return true;
    }
    return false;
  });
}

export const SUGGESTIONS = ["forecast", "chatbot", "contract", "substation", "asset", "procurement", "report", "code", "customer"];
