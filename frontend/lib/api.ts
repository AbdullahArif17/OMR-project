import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type {
  AccountUser,
  AnswerKeyPayload,
  AnswerMap,
  ApiEnvelope,
  CreateExamInput,
  Exam,
  Result,
  ResultsPayload,
  ScanBatchPayload,
  ScanSheetInput,
  TokenPayload,
} from "@/lib/types";

const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const client = axios.create({
  baseURL: apiUrl,
  timeout: 120_000,
  headers: { Accept: "application/json" },
});

type AccessTokenProvider = () => string | null;
type UnauthorizedHandler = () => Promise<string | null>;

let tokenProvider: AccessTokenProvider = () => null;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setAccessTokenProvider(provider: AccessTokenProvider) {
  tokenProvider = provider;
}

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

// Requests that carry their own credentials (login/refresh) opt out of both the
// bearer header and the refresh-on-401 retry to avoid recursion.
interface RetryableConfig extends InternalAxiosRequestConfig {
  skipAuth?: boolean;
  _retried?: boolean;
}

client.interceptors.request.use((config: RetryableConfig) => {
  if (config.skipAuth) return config;
  const token = tokenProvider();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetryableConfig | undefined;
    const status = error.response?.status;
    if (
      status === 401 &&
      config &&
      !config.skipAuth &&
      !config._retried &&
      unauthorizedHandler
    ) {
      config._retried = true;
      const refreshed = await unauthorizedHandler();
      if (refreshed) {
        config.headers.Authorization = `Bearer ${refreshed}`;
        return client(config);
      }
    }
    return Promise.reject(error);
  },
);

function unwrap<T>(payload: ApiEnvelope<T> | T): T {
  if (payload && typeof payload === "object" && "success" in payload) {
    const envelope = payload as ApiEnvelope<T>;
    if (!envelope.success) throw new Error(envelope.message || "The request was not successful.");
    return envelope.data;
  }
  return payload as T;
}

function pathId(id: string) {
  return encodeURIComponent(id);
}

export function getApiError(error: unknown, fallback = "Something went wrong. Please try again.") {
  if (axios.isAxiosError(error)) {
    if (error.code === "ERR_CANCELED") return "Scanning was canceled. Your queued files were kept.";
    const response = (error as AxiosError<Record<string, unknown>>).response?.data;
    const detail = response?.detail;
    const message = response?.message;
    const responseData = response?.data;
    if (responseData && typeof responseData === "object") {
      const failures = (responseData as { errors?: unknown }).errors;
      if (Array.isArray(failures) && failures.length > 0) {
        const failureText = failures
          .map((item) => {
            if (!item || typeof item !== "object") return String(item);
            const failure = item as { filename?: unknown; message?: unknown };
            const name = typeof failure.filename === "string" ? `${failure.filename}: ` : "";
            return `${name}${String(failure.message || "Could not be processed")}`;
          })
          .join(" · ");
        return `${typeof message === "string" ? `${message} ` : ""}${failureText}`.trim();
      }
    }
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) return String(item.msg);
          return String(item);
        })
        .join(" ");
    }
    if (typeof message === "string") return message;
    if (error.code === "ECONNABORTED") return "The server took too long to respond. Please try again.";
    if (!error.response) {
      return `Could not reach the OMR API at ${apiUrl}. Check that the backend is running.`;
    }
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

export const api = {
  baseUrl: apiUrl,

  async adminLogin(password: string) {
    const response = await client.post<ApiEnvelope<TokenPayload>>(
      "/auth/admin/login",
      { password },
      { skipAuth: true } as RetryableConfig,
    );
    return unwrap(response.data);
  },

  async me() {
    const response = await client.get<ApiEnvelope<AccountUser>>("/auth/me");
    return unwrap(response.data);
  },



  async listExams() {
    const response = await client.get<ApiEnvelope<Exam[]> | Exam[]>("/exams");
    const data = unwrap(response.data);
    if (Array.isArray(data)) return data;
    const nested = data as unknown as { exams?: Exam[] };
    return nested.exams ?? [];
  },

  async getExam(id: string) {
    const response = await client.get<ApiEnvelope<Exam> | Exam>(`/exams/${pathId(id)}`);
    return unwrap(response.data);
  },

  async createExam(input: CreateExamInput) {
    const response = await client.post<ApiEnvelope<Exam> | Exam>("/exams", input);
    return unwrap(response.data);
  },

  async deleteExam(id: string) {
    const response = await client.delete<ApiEnvelope<unknown>>(`/exams/${pathId(id)}`);
    return unwrap(response.data);
  },

  async getAnswerKey(id: string) {
    const response = await client.get<ApiEnvelope<AnswerKeyPayload | AnswerMap> | AnswerKeyPayload | AnswerMap>(
      `/exams/${pathId(id)}/answer-key`,
    );
    return unwrap(response.data);
  },

  async saveManualAnswerKey(id: string, answers: AnswerMap) {
    const response = await client.post<ApiEnvelope<AnswerKeyPayload> | AnswerKeyPayload>(
      `/exams/${pathId(id)}/answer-key/manual`,
      { answers },
    );
    return unwrap(response.data);
  },

  async scanAnswerKey(id: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    const response = await client.post<ApiEnvelope<AnswerKeyPayload> | AnswerKeyPayload>(
      `/exams/${pathId(id)}/answer-key/scan`,
      form,
      { timeout: 180_000 },
    );
    return unwrap(response.data);
  },

  async uploadAnswerKeyCsv(id: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    const response = await client.post<ApiEnvelope<AnswerKeyPayload> | AnswerKeyPayload>(
      `/exams/${pathId(id)}/answer-key/csv`,
      form,
    );
    return unwrap(response.data);
  },

  async scanSheets(
    id: string,
    sheets: ScanSheetInput[],
    options: {
      signal?: AbortSignal;
      onProgress?: (value: number) => void;
      idempotencyKey?: string;
    } = {},
  ) {
    const form = new FormData();
    sheets.forEach((sheet) => {
      form.append("files", sheet.file);
    });
    form.append(
      "metadata",
      JSON.stringify(
        sheets.map((sheet) => ({
          name: sheet.studentName.trim(),
          roll_number: sheet.rollNumber.trim(),
          class_name: sheet.className.trim(),
        })),
      ),
    );
    const response = await client.post<ApiEnvelope<ScanBatchPayload | Result[]> | ScanBatchPayload | Result[]>(
      `/exams/${pathId(id)}/scan`,
      form,
      {
        headers: options.idempotencyKey
          ? { "Idempotency-Key": options.idempotencyKey }
          : undefined,
        signal: options.signal,
        timeout: 600_000,
        onUploadProgress: (event) => {
          if (!options.onProgress || !event.total) return;
          options.onProgress(Math.min(95, Math.round((event.loaded / event.total) * 95)));
        },
      },
    );
    const data = unwrap(response.data);
    if (Array.isArray(data)) return { results: data } satisfies ScanBatchPayload;
    return data;
  },

  async getResults(id: string) {
    const response = await client.get<ApiEnvelope<ResultsPayload | Result[]> | ResultsPayload | Result[]>(
      `/exams/${pathId(id)}/results`,
    );
    const data = unwrap(response.data);
    if (Array.isArray(data)) return { results: data } satisfies ResultsPayload;
    return data;
  },

  async getResult(id: string) {
    const response = await client.get<ApiEnvelope<Result> | Result>(`/results/${pathId(id)}`);
    return unwrap(response.data);
  },

  async exportResults(id: string) {
    const response = await client.get<Blob>(`/exams/${pathId(id)}/results/export`, {
      responseType: "blob",
    });
    return response.data;
  },
};
