export interface Owner {
  id: number;
  name: string;
  department: string | null;
  category: string | null; // business unit
}

export interface TypeRef {
  id: number;
  name: string;
  description: string | null;
}

export interface Initiative {
  id: number;
  name: string;
  description: string | null;
  status: string;
  date_start: string | null;
  date_delivery: string | null;
  value_score: number | null;
  solution_complexity_score: number | null;
  owner: Owner | null;
  solution_type: TypeRef | null;
  value_type: TypeRef | null;
}

export interface InitiativePage {
  items: Initiative[];
  total: number;
  limit: number;
  offset: number;
}
