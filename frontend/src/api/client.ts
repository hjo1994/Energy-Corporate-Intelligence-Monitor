import { serviceApi } from "../shared/api/serviceApi";
import type { Initiative, InitiativeInput, InitiativePage, Owner, TypeRef } from "./types";

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
  if (status === 401) return new ApiError(status, "You are not signed in, or your session has expired. Please sign in again.");
  if (status === 403) return new ApiError(status, "You do not have permission to view this data.");
  if (status === 503) return new ApiError(status, "The database is temporarily unavailable. Please try again shortly.");
  if (status === null) return new ApiError(null, "The backend cannot be reached.");
  return new ApiError(status, `The data could not be loaded (HTTP ${status}).`);
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

// ---------- input form ----------

export interface ReferenceData {
  owners: Owner[];
  valueTypes: TypeRef[];
  solutionTypes: TypeRef[];
}

export async function fetchReferenceData(): Promise<ReferenceData> {
  try {
    const [owners, valueTypes, solutionTypes] = await Promise.all([
      serviceApi.get<Owner[]>("/owners"),
      serviceApi.get<TypeRef[]>("/value-types"),
      serviceApi.get<TypeRef[]>("/solution-types"),
    ]);
    return {
      owners,
      valueTypes: valueTypes.map((t) => clean(t) as TypeRef),
      solutionTypes: solutionTypes.map((t) => clean(t) as TypeRef),
    };
  } catch (err) {
    throw toApiError(err);
  }
}

/** Stores a new initiative; it comes back as "pending" until the pipeline has processed it. */
export async function createInitiative(input: InitiativeInput): Promise<Initiative> {
  try {
    const created = await serviceApi.post<Initiative>("/initiatives", input);
    return { ...created, solution_type: clean(created.solution_type), value_type: clean(created.value_type) };
  } catch (err) {
    const response = (err as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response;
    // 409 (name already taken in the business unit) and 422 carry a message for the user
    if (response?.status === 409 && typeof response.data?.detail === "string") {
      throw new ApiError(409, response.data.detail);
    }
    if (response?.status === 422) {
      throw new ApiError(422, "Some values were rejected by the server. Please check the form.");
    }
    throw toApiError(err);
  }
}

/** Feature switches of this installation; the input form is hidden unless the backend allows it. */
export async function fetchFeatures(): Promise<{ initiative_input: boolean }> {
  try {
    return await serviceApi.get<{ initiative_input: boolean }>("/features");
  } catch {
    return { initiative_input: false };
  }
}
