export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  message: string;
}

export interface Exam {
  id: string;
  name: string;
  subject?: string | null;
  total_questions: number;
  options_per_question: number;
  created_by?: string | null;
  created_at: string;
  answer_key_count?: number;
  result_count?: number;
}

export interface CreateExamInput {
  name: string;
  subject?: string;
  total_questions: number;
  options_per_question: 4 | 5;
}

export type AnswerMap = Record<string, string>;

export interface AnswerKeyPayload {
  exam_id?: string;
  answers: AnswerMap;
  count?: number;
}

export interface Student {
  id?: string;
  name?: string | null;
  roll_number?: string | null;
  class_name?: string | null;
  class?: string | null;
}

export interface QuestionBreakdown {
  question?: number;
  student?: string | null;
  selected_answer?: string | null;
  correct?: string | null;
  correct_answer?: string | null;
  result?: boolean | "correct" | "incorrect" | "unanswered";
  is_correct?: boolean;
}

export interface Result {
  id: string;
  exam_id: string;
  student_id?: string | null;
  student?: Student | null;
  student_name?: string | null;
  roll_number?: string | null;
  class_name?: string | null;
  score: number;
  total: number;
  percentage: number;
  answers?: AnswerMap | null;
  breakdown?: Record<string, QuestionBreakdown> | QuestionBreakdown[] | null;
  scanned_at: string;
  filename?: string | null;
  source_file?: string | null;
  exam?: Exam | null;
}

export interface ScanSheetInput {
  file: File;
  studentName: string;
  rollNumber: string;
  className: string;
}

export interface ScanFailure {
  filename: string;
  message: string;
}

export interface ScanBatchPayload {
  results: Result[];
  errors?: ScanFailure[];
  processed?: number;
  processed_count?: number;
  failed_count?: number;
}

export interface ResultsSummary {
  total_students?: number;
  total_scans?: number;
  average_score: number;
  average_percentage: number;
  highest_score: number;
  lowest_score: number;
  pass_rate: number;
}

export interface ResultsPayload {
  results: Result[];
  summary?: ResultsSummary;
}

export type Grade = "A" | "B" | "C" | "D" | "F";
