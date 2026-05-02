export type MediaType = "video" | "audio";

export interface VocabularyItem {
  term: string;
  meaning: string;
  nuance: string;
  example: string;
}

export interface LessonChunk {
  id: string;
  start: number;
  end: number;
  sourceText: string;
  translation: string;
  readThrough: string;
  vocabulary: VocabularyItem[];
}

export interface Lesson {
  media: {
    type: MediaType;
    path: string;
    duration: number;
    title: string;
  };
  languages: {
    source: string;
    target: string;
  };
  chunks: LessonChunk[];
}

