// Hand-written API types for the report and error envelope.
// Replaced by generated types from the OpenAPI document on Day 8.

export type ExtractionWarning = {
  code: string;
  message: string;
  page: number | null;
};

export type ReportMeta = {
  filename: string;
  size_bytes: number;
  page_count: number;
  method: string;
  duration_ms: number;
  warnings: ExtractionWarning[];
};

export type ExtractedTextPage = {
  page_number: number;
  row_text: string;
  column_text: string | null;
};

export type ExtractedText = {
  pages: ExtractedTextPage[];
  char_count: number;
  method: string;
  warnings: ExtractionWarning[];
};

export type AnalysisReport = {
  schema_version: number;
  engine_version: string;
  dictionary_version: number;
  meta: ReportMeta;
  extracted_text: ExtractedText;
};

export type ErrorEnvelope = {
  code: string;
  message: string;
};

export type Health = {
  version: string;
  engine_version: string;
  dictionary_version: number;
  limits: {
    max_file_bytes: number;
    max_pages: number;
    max_jd_chars: number;
  };
};
