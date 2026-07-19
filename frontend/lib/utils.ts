import type {
  AnswerMap,
  Grade,
  QuestionBreakdown,
  Result,
  ResultsSummary,
} from "@/lib/types";

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function formatDate(value?: string | null, includeTime = false) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    ...(includeTime ? { hour: "numeric", minute: "2-digit" } : {}),
  }).format(date);
}

export function getInitials(value?: string | null) {
  if (!value) return "T";
  const parts = value.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function getGrade(percentage: number): Grade {
  if (percentage >= 90) return "A";
  if (percentage >= 80) return "B";
  if (percentage >= 60) return "C";
  if (percentage >= 40) return "D";
  return "F";
}

export function gradeTone(percentage: number) {
  if (percentage >= 60) {
    return {
      badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
      bar: "bg-emerald-500",
      text: "text-emerald-700",
    };
  }
  if (percentage >= 40) {
    return {
      badge: "bg-amber-50 text-amber-700 ring-amber-600/20",
      bar: "bg-amber-500",
      text: "text-amber-700",
    };
  }
  return {
    badge: "bg-rose-50 text-rose-700 ring-rose-600/20",
    bar: "bg-rose-500",
    text: "text-rose-700",
  };
}

export function studentName(result: Result) {
  return result.student?.name || result.student_name || "Unnamed student";
}

export function studentRoll(result: Result) {
  return result.student?.roll_number || result.roll_number || "—";
}

export function studentClass(result: Result) {
  return result.student?.class_name || result.student?.class || result.class_name || "—";
}

export function normalizeAnswerMap(value: unknown): AnswerMap {
  if (!value) return {};
  if (Array.isArray(value)) {
    return value.reduce<AnswerMap>((answers, item, index) => {
      if (typeof item === "string") {
        answers[String(index + 1)] = item.toUpperCase();
      } else if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        const question = row.question_number ?? row.question ?? index + 1;
        const answer = row.correct_answer ?? row.answer;
        if (answer) answers[String(question)] = String(answer).toUpperCase();
      }
      return answers;
    }, {});
  }
  if (typeof value === "object") {
    const object = value as Record<string, unknown>;
    if (object.answers) return normalizeAnswerMap(object.answers);
    if (object.answer_key) return normalizeAnswerMap(object.answer_key);
    return Object.entries(object).reduce<AnswerMap>((answers, [question, answer]) => {
      if (typeof answer === "string") answers[question] = answer.toUpperCase();
      return answers;
    }, {});
  }
  return {};
}

export function breakdownRows(result: Result): Array<QuestionBreakdown & { question: number }> {
  const source = result.breakdown;
  if (Array.isArray(source)) {
    return source.map((row, index) => ({ ...row, question: row.question ?? index + 1 }));
  }
  if (source && typeof source === "object") {
    return Object.entries(source).map(([question, row]) => ({
      question: Number(question),
      ...(row as QuestionBreakdown),
    }));
  }
  const answers = normalizeAnswerMap(result.answers);
  return Object.entries(answers).map(([question, student]) => ({
    question: Number(question),
    student,
  }));
}

export function isCorrect(row: QuestionBreakdown) {
  return row.is_correct === true || row.result === true || row.result === "correct";
}

export function calculateSummary(results: Result[]): ResultsSummary {
  if (results.length === 0) {
    return {
      total_students: 0,
      average_score: 0,
      average_percentage: 0,
      highest_score: 0,
      lowest_score: 0,
      pass_rate: 0,
    };
  }
  const scores = results.map((result) => Number(result.score) || 0);
  const percentages = results.map((result) => Number(result.percentage) || 0);
  return {
    total_students: results.length,
    average_score: scores.reduce((sum, value) => sum + value, 0) / results.length,
    average_percentage:
      percentages.reduce((sum, value) => sum + value, 0) / results.length,
    highest_score: Math.max(...scores),
    lowest_score: Math.min(...scores),
    pass_rate:
      (percentages.filter((percentage) => percentage >= 60).length / results.length) * 100,
  };
}

export function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function safeFileName(value: string) {
  return value.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-|-$/g, "");
}
