import { serviceApi } from "../shared/api/serviceApi";
import type { Initiative, InitiativePage, TypeRef } from "./types";

const PAGE_SIZE = 500; // backend maximum

export class ApiError extends Error {
  constructor(
    public status: number | null,
    message: string,
  ) {
    super(message);
  }
}

// ServiceApi is axios underneath: failed requests arrive as errors carrying `response.status`.
function toApiError(err: unknown): ApiError {
  const status = (err as { response?: { status?: number } } | null)?.response?.status ?? null;
  if (status === 401) return new ApiError(status, "Sie sind nicht angemeldet oder die Sitzung ist abgelaufen. Bitte neu anmelden.");
  if (status === 403) return new ApiError(status, "Für diese Daten fehlt die Berechtigung.");
  if (status === 503) return new ApiError(status, "Die Datenbank ist gerade nicht erreichbar. Bitte gleich erneut versuchen.");
  if (status === null) return new ApiError(null, "Das Backend ist nicht erreichbar.");
  return new ApiError(status, `Die Daten konnten nicht geladen werden (HTTP ${status}).`);
}

async function getPage(offset: number): Promise<InitiativePage> {
  try {
    const page = await serviceApi.get<InitiativePage>("/initiatives", {
      limit: PAGE_SIZE,
      offset,
      sort: "name",
    });
    return cleanPage(page);
  } catch (err) {
    throw toApiError(err);
  }
}

// The Variables sheet contains zero-width characters inside catalog names
// ("Connection lif<U+FEFF>ecycle"); the backend keeps them verbatim, the UI shows clean text.
const INVISIBLE = /[​-‍﻿]/g;
const clean = (t: TypeRef | null): TypeRef | null => t && { ...t, name: t.name.replace(INVISIBLE, "") };

export function cleanPage(page: InitiativePage): InitiativePage {
  return {
    ...page,
    items: page.items.map((i) => ({ ...i, solution_type: clean(i.solution_type), value_type: clean(i.value_type) })),
  };
}

// Filtering, sorting and the KPI tiles all work on the complete set in the
// browser, so every page is fetched up front.
export async function fetchAllInitiatives(): Promise<Initiative[]> {
  const items: Initiative[] = [];
  for (;;) {
    const page = await getPage(items.length);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}
