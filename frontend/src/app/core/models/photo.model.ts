export interface ProjectPhotoRead {
  id: number;
  project_slug: string;
  section_number: number | null;
  daily_report_id: number | null;
  user_id: number | null;
  username: string | null;
  filename: string;
  view_url: string;
  annotated_url: string | null;
  content_type: string | null;
  sha256: string;
  width: number | null;
  height: number | null;
  taken_at: string | null;
  geo_lat: number | null;
  geo_lng: number | null;
  caption: string | null;
  created_at: string;
}

export interface ProjectPhotoUpdate {
  caption?: string | null;
  section_number?: number | null;
  daily_report_id?: number | null;
}

export interface PhotoUploadOptions {
  sectionNumber?: number | null;
  dailyReportId?: number | null;
  caption?: string | null;
}
