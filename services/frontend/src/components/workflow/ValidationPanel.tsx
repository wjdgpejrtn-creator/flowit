import type { ValidationErrorResponse, ValidationErrorItem } from '@common/generated';
import { ErrorCode } from '@common/generated';

const ERROR_CODE_LABEL: Record<ErrorCode, string> = {
  [ErrorCode.E_NODE_TYPE_MISMATCH]:   '노드 타입 불일치',
  [ErrorCode.E_CYCLE_DETECTED]:       '순환 감지',
  [ErrorCode.E_ISOLATED_NODE]:        '고립된 노드',
  [ErrorCode.E_DUPLICATE_ID]:         '중복 ID',
  [ErrorCode.E_PERMISSION_DENIED]:    '권한 없음',
  [ErrorCode.E_MISSING_CONNECTION]:   '연결 누락',
  [ErrorCode.E_INVALID_TRIGGER]:      '잘못된 트리거',
};

function ErrorItem({ item }: { item: ValidationErrorItem }) {
  return (
    <div className="border-[1.5px] border-[var(--color-risk-restricted)] rounded-[4px_8px_4px_8px] p-[8px] bg-red-50 flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold text-[var(--color-risk-restricted)]">
          {ERROR_CODE_LABEL[item.code] ?? item.code}
        </span>
        <span className="text-[10px] text-[var(--color-ink4)] font-mono">{item.validator}</span>
      </div>
      <p className="text-[12px] text-[var(--color-ink2)]">{item.message}</p>
      {item.hint && (
        <p className="text-[11px] text-[var(--color-ink3)] italic">💡 {item.hint}</p>
      )}
      {item.node_ids.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.node_ids.map((id) => (
            <span key={id} className="font-mono text-[10px] border border-[var(--color-ink4)] rounded px-1 bg-white text-[var(--color-ink3)]">
              {id.slice(0, 8)}…
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  result: ValidationErrorResponse | null;
  loading?: boolean;
}

export default function ValidationPanel({ result, loading }: Props) {
  if (loading) {
    return (
      <div className="p-3 text-[12px] text-[var(--color-ink4)] italic">검증 중…</div>
    );
  }

  if (!result) {
    return (
      <div className="p-3 text-[12px] text-[var(--color-ink4)] italic">
        검증 결과가 없습니다.
      </div>
    );
  }

  const passed = result.validation_status === 'passed';

  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="flex items-center gap-2">
        <span
          className="font-bold text-[13px]"
          style={{ color: passed ? 'var(--color-risk-low)' : 'var(--color-risk-restricted)' }}
        >
          {passed ? '✓ 검증 통과' : `✗ 검증 실패 (${result.errors.length}개)`}
        </span>
      </div>
      {!passed && result.errors.map((err, i) => (
        <ErrorItem key={i} item={err} />
      ))}
    </div>
  );
}
