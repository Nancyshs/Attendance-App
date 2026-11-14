export type Role = 'admin' | 'staff' | 'trainer'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  trainer_id: number | null
  is_active: boolean
  last_login_at: string | null
}

export interface Trainee {
  id: number
  badge_id: string
  full_name: string
  governorate: string | null
  job_title: string | null
  organization: string | null
  national_id: string | null
  email: string | null
  phone: string | null
  group_name: string | null
  notes: string | null
  is_active: boolean
  photo_url: string | null
  qr_token: string | null
  created_at: string
}

export interface TraineeBrief {
  id: number
  badge_id: string
  full_name: string
  group_name: string | null
  photo_url: string | null
}

export interface Trainer {
  id: number
  name: string
  email: string | null
  is_active: boolean
}

export interface TrainingDay {
  id: number
  date: string
  start_time: string
  end_time: string
  late_after: string
  checkout_from: string
  note: string | null
  is_auto: boolean
}

export type SurveyState = 'not_open' | 'open' | 'closed' | 'cancelled' | 'submitted' | 'not_attended'

export interface Session {
  id: number
  day: string
  start_time: string
  end_time: string
  title: string
  description: string | null
  trainer_id: number | null
  trainer_name: string | null
  room: string | null
  template_id: number | null
  axis: string | null
  survey_token: string
  survey_url: string
  survey_duration_minutes: number | null
  effective_duration_minutes: number
  survey_opens_at: string | null
  survey_closes_at: string | null
  survey_until_end_of_day: boolean
  require_attendance: boolean
  survey_state: SurveyState
  effective_opens_at: string
  effective_closes_at: string
  is_cancelled: boolean
  submissions: number
  exam_token: string
  exam_url: string
  exam_before_opens_at: string | null
  exam_before_closes_at: string | null
  exam_after_opens_at: string | null
  exam_after_closes_at: string | null
  exam_state: SurveyState
  exam_phase: 'before' | 'after' | null
  exam_questions: { id: number; text: string; correct: boolean }[]
}

export interface ScanResult {
  ok: boolean
  action: 'check_in' | 'check_out' | 'duplicate' | 'rejected'
  code: string
  message: string
  status: string | null
  early_leave: boolean
  trainee: TraineeBrief | null
  check_in_at: string | null
  check_out_at: string | null
  worked_minutes: number | null
  scanned_at: string | null
  replayed: boolean
}

export type AttendanceStatus = 'present' | 'late' | 'absent' | 'excused' | 'not_arrived' | 'upcoming' | 'no_training'

export interface AttendanceRow {
  trainee: TraineeBrief
  status: AttendanceStatus
  early_leave: boolean
  incomplete: boolean
  worked_minutes: number | null
  check_in_at: string | null
  check_out_at: string | null
  check_in_source: string | null
  excused: boolean
  is_manual: boolean
  note: string | null
}

export interface AttendanceDayResponse {
  date: string
  training_day: { start_time: string; end_time: string; late_after: string; checkout_from: string } | null
  rows: AttendanceRow[]
}

export interface Alert {
  type: 'absences' | 'low_rating'
  severity: 'high' | 'medium'
  title: string
  value: number
  badge_id?: string
  trainer_name?: string
  day?: string
  trainee_id?: number
  session_id?: number
}

export interface Dashboard {
  date: string
  program_name: string
  has_training_day: boolean
  day: { start_time: string; end_time: string; late_after: string; is_over: boolean } | null
  totals: {
    active: number
    arrived: number
    on_time: number
    late: number
    checked_out: number
    excused: number
    not_arrived: number
    early_leave: number
    present_now: number
  }
  recent_scans: {
    id: number
    at: string
    action: string
    ok: boolean
    message: string
    source: string
    trainee_name: string | null
    badge_id: string | null
  }[]
  sessions: {
    id: number
    title: string
    start_time: string
    end_time: string
    trainer_name: string | null
    room: string | null
    survey_state: SurveyState
    survey_opens_at: string
    survey_closes_at: string
    submissions: number
    is_cancelled: boolean
  }[]
  alerts: Alert[]
  server_time: string
  local_time: string
}

export interface AttendanceReport {
  from: string
  to: string
  days: { date: string; start_time: string; end_time: string; is_over: boolean }[]
  trainees: {
    trainee: TraineeBrief & { is_active: boolean }
    summary: {
      present: number
      late: number
      absent: number
      excused: number
      early_leave: number
      incomplete: number
      attendance_pct: number | null
      avg_hours: number | null
    }
    cells: {
      date: string
      status: AttendanceStatus
      early_leave: boolean
      incomplete: boolean
      check_in_at: string | null
      check_out_at: string | null
      worked_minutes: number | null
      excused: boolean
      note: string | null
      is_manual: boolean
    }[]
  }[]
}

export interface QuestionStat {
  question_id: number
  text: string
  type: 'rating' | 'nps' | 'choice' | 'text'
  avg: number | null
  percent: number | null
  count: number
  distribution?: Record<string, number>
  choices?: Record<string, number>
}

export interface SurveyReport {
  overall: { sessions: number; responses: number; avg_rating: number | null }
  sessions: {
    id: number
    title: string
    day: string
    start_time: string
    end_time: string
    trainer_id: number | null
    trainer_name: string | null
    room: string | null
    avg_rating: number | null
    percent: number | null
    responses: number
    eligible: number
    response_rate: number | null
    nps: number | null
    questions: QuestionStat[]
    comments: { question: string; text: string; submitted_at: string }[]
  }[]
  trainers: { trainer_id: number | null; trainer_name: string; avg_rating: number; responses: number; sessions: number }[]
  trend: { day: string; avg_rating: number }[]
  comments: { session_title: string; day: string; trainer_name: string | null; question: string; text: string; submitted_at: string }[]
}

export interface SurveyRespondent {
  response_id: number
  submitted_at: string
  trainee: {
    id: number
    full_name: string
    badge_id: string
    governorate: string | null
    job_title: string | null
    organization: string | null
    national_id: string | null
    phone: string | null
    email: string | null
    group_name: string | null
  }
  session: { id: number; title: string; axis: string | null; day: string; trainer_name: string | null }
  answers: { question_id: number; text: string; type: 'rating' | 'nps' | 'choice' | 'text'; position: number; value: number | string | null }[]
}

export interface Question {
  id?: number
  text: string
  type: 'rating' | 'nps' | 'choice' | 'text'
  options: string[] | null
  required: boolean
}

export interface Template {
  id: number
  name: string
  description: string | null
  is_anonymous: boolean
  is_default: boolean
  is_active: boolean
  questions: (Question & { id: number; position: number; is_active: boolean })[]
}

export interface AuditEntry {
  id: number
  at: string
  username: string | null
  action: string
  entity: string | null
  entity_id: string | null
  details: Record<string, unknown> | null
  ip: string | null
}

export interface Settings {
  program_name: string
  day_start_time: string
  day_end_time: string
  late_after_minutes: number
  checkout_from_time: string
  min_checkout_gap_minutes: number
  working_weekdays: number[]
  survey_program_name: string
  survey_duration_minutes: number
  survey_opens_minutes_before_end: number
  survey_close_hours_after_end: number
  require_attendance_for_survey: boolean
  absence_alert_threshold: number
  low_rating_threshold: number
}

// ------------------------------------------------------------------ portal
export interface PortalSession {
  id: number
  title: string
  day: string
  start_time: string
  end_time: string
  trainer_name: string | null
  room: string | null
  state: SurveyState
  opens_at: string
  closes_at: string
}

export interface PortalMe {
  trainee: TraineeBrief
  program_name: string
  today: { date: string; check_in_at: string | null; check_out_at: string | null }
  sessions: PortalSession[]
  server_time: string
}

export interface PortalSurvey {
  session: { id: number; title: string; day: string; start_time: string; end_time: string; trainer_name: string | null }
  state: SurveyState
  opens_at: string
  closes_at: string
  is_anonymous: boolean
  questions: { id: number; text: string; type: 'rating' | 'nps' | 'choice' | 'text'; options: string[] | null; required: boolean }[]
}

export interface SurveyQuestionDef {
  id: number
  text: string
  type: 'rating' | 'nps' | 'choice' | 'text'
  options: string[] | null
  required: boolean
}

/** Public (QR) survey of one session. */
export interface PublicSurvey {
  program_name: string
  session: { id: number; title: string; axis: string | null; day: string; start_time: string; end_time: string; trainer_name: string | null; room: string | null }
  state: SurveyState
  opens_at: string
  closes_at: string
  server_time: string
  questions: SurveyQuestionDef[]
}