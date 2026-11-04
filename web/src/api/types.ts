// Hand-written API types for the report and error envelope.
// Replaced by generated types from the OpenAPI document on Day 8.

export type ExtractionWarningCode = "columns_suspected";

export type ExtractionWarning = {
  code: ExtractionWarningCode;
  message: string;
  page: number | null;
};

export type ReadingOrder = "row" | "column";

export type SectionName =
  | "contact"
  | "summary"
  | "experience"
  | "education"
  | "skills"
  | "projects"
  | "certifications";

export type SectionFinding = {
  name: SectionName;
  found: boolean;
  heading: string | null;
  page: number | null;
  line: number | null;
};

export type ContactItem = {
  found: boolean;
  value: string | null;
  page: number | null;
  line: number | null;
};

export type ContactInfo = {
  email: ContactItem;
  phone: ContactItem;
  linkedin: ContactItem;
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
  reading_order: ReadingOrder[];
  sections: SectionFinding[];
  contact: ContactInfo;
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
