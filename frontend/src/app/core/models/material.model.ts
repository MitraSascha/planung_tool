export interface MaterialItem {
  id: number;
  section_number: number | null;
  kind: string;
  name: string;
  soll_qty: number | null;
  ist_qty: number | null;
  unit: string | null;
  location: string | null;
  status: string;
  note: string | null;
  /** Herkunft: 'offer' | 'manual' | 'artikelstamm' | 'daily_report_freitext'.
   *  Wichtig für Nachkalkulation — filter('artikelstamm') zeigt alle nicht
   *  im Angebot enthaltenen Posten = potentielle Nachträge. */
  source?: string;
  artikelstamm_artikelnummer?: string | null;
  artikelstamm_preis_eur?: number | null;
}

/** Treffer aus der Artikelstamm-Suche (DATANORM-Großhandels-DB). */
export interface ArticleHit {
  artikelnummer: string;
  kurztext1?: string | null;
  kurztext2?: string | null;
  warengruppe?: string | null;
  mengeneinheit?: string | null;
  preis_eur?: number | null;
  hersteller?: string | null;
  hersteller_artikelnummer?: string | null;
  ean?: string | null;
}

export interface MaterialUsageCreate {
  material_item_id: number;
  daily_report_id?: number | null;
  section_number?: number | null;
  qty_used: number;
  unit?: string | null;
  used_at: string; // ISO date YYYY-MM-DD
  notes?: string | null;
}

export interface MaterialUsageRead {
  id: number;
  material_item_id: number | null;
  material_item_name: string | null;
  daily_report_id: number | null;
  user_id: number | null;
  username: string | null;
  section_number: number | null;
  qty_used: number;
  unit: string | null;
  used_at: string;
  notes: string | null;
  created_at: string;
}

export interface MaterialPerItem {
  item_id: number;
  name: string;
  kind: string;
  section_number: number | null;
  section_name: string | null;
  soll_qty: number | null;
  ist_qty: number | null;
  remaining: number | null;
  percent_done: number | null;
  status: string;
  unit: string | null;
  usage_count: number;
  last_used_at: string | null;
}

export interface MaterialPerSection {
  section_number: number | null;
  section_name: string | null;
  items_total: number;
  items_completed: number;
  total_soll: number;
  total_ist: number;
  percent_done: number | null;
}

export interface MaterialWeeklyPoint {
  week_start: string;
  total_qty_used: number;
  usage_count: number;
}

export interface MaterialTopItem {
  item_id: number | null;
  name: string;
  total_used: number;
  unit: string | null;
}

export interface MaterialAnalytics {
  project_slug: string;
  items_total: number;
  items_completed: number;
  items_overrun: number;
  total_soll: number;
  total_ist: number;
  percent_done: number | null;
  usage_count: number;
  per_item: MaterialPerItem[];
  per_section: MaterialPerSection[];
  weekly_burndown: MaterialWeeklyPoint[];
  top_items: MaterialTopItem[];
}
