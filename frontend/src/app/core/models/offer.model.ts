export type OfferSourceType = 'xlsx' | 'csv' | 'ugl' | 'pdf' | 'manual';

export interface OfferItem {
  id?: number;
  position_index: number;
  position_label?: string | null;
  article_no?: string | null;
  name?: string | null;
  description?: string | null;
  qty?: number | null;
  unit?: string | null;
  unit_price_net_eur?: number | null;
  total_net_eur?: number | null;
  vat_rate?: number | null;
  notes?: string | null;
}

export interface OfferSummary {
  id: number;
  project_slug: string;
  supplier_name: string;
  offer_no?: string | null;
  offer_date?: string | null;
  currency: string;
  total_net_eur?: number | null;
  total_gross_eur?: number | null;
  source_type: OfferSourceType;
  source_file?: string | null;
  attached_file_path?: string | null;
  imported_at: string;
  item_count: number;
}

export interface OfferRead {
  id: number;
  project_slug: string;
  supplier_name: string;
  offer_no?: string | null;
  offer_date?: string | null;
  currency: string;
  total_net_eur?: number | null;
  total_gross_eur?: number | null;
  vat_rate?: number | null;
  notes?: string | null;
  source_type: OfferSourceType;
  source_file?: string | null;
  attached_file_path?: string | null;
  imported_at: string;
  imported_by_user_id?: number | null;
  imported_by_username?: string | null;
  updated_at: string;
  items: OfferItem[];
}

export interface OfferImportPreview {
  source_type: OfferSourceType;
  source_file: string;
  offer: {
    supplier_name: string;
    offer_no?: string | null;
    offer_date?: string | null;
    currency: string;
    total_net_eur?: number | null;
    total_gross_eur?: number | null;
    vat_rate?: number | null;
    notes?: string | null;
  };
  items: OfferItem[];
  warnings: string[];
  detected_columns: Record<string, string>;
}

export interface OfferImporterInfo {
  source_name: string;
  display_name: string;
  accepts_extensions: string;
}

export interface OfferPdfUploadForm {
  supplier_name: string;
  offer_no?: string;
  offer_date?: string;
  total_net_eur?: number;
  total_gross_eur?: number;
  vat_rate?: number;
  notes?: string;
}
