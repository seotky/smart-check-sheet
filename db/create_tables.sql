-- ユーザーテーブル
CREATE TABLE users (
    user_id VARCHAR(255) PRIMARY KEY,
    user_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェックシートテーブル
CREATE TABLE check_sheets (
    check_sheet_id VARCHAR(255) PRIMARY KEY,
    check_status ENUM('checking', 'review_waiting', 'returned', 'completed') NOT NULL COMMENT 'checking: チェック中, review_waiting: レビュー待ち, returned: 差し戻し, completed: 完了',
    created_by VARCHAR(255) NOT NULL COMMENT 'チェックシート作成者ID',
    reviewer_id VARCHAR(255) COMMENT 'レビュアーのユーザーID',
    check_group_id BIGINT UNSIGNED COMMENT 'チェックグループID',
    check_remarks TEXT COMMENT 'チェック時の備考',
    review_remarks TEXT COMMENT 'レビュー時の備考',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(user_id),
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id),
    FOREIGN KEY (check_group_id) REFERENCES check_groups(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェック・レビュー結果テーブル
CREATE TABLE check_results (
    check_sheet_id VARCHAR(255) NOT NULL,
    check_id BIGINT UNSIGNED NOT NULL COMMENT 'check_itemsテーブルのidを参照',
    check_type ENUM('check', 'review') NOT NULL COMMENT 'check: 1次チェック, review: レビュー',
    checked BOOLEAN NOT NULL COMMENT 'チェック結果（True/False）',
    user_id VARCHAR(255) NOT NULL COMMENT 'チェック/レビュー実施者のID',
    remarks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (check_sheet_id, check_id, check_type),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (check_sheet_id) REFERENCES check_sheets(check_sheet_id),
    FOREIGN KEY (check_id) REFERENCES check_items(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェックシートのカテゴリーテーブル
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェックシートのグループテーブル
CREATE TABLE check_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ユーザーとチェックグループの紐づけテーブル（1対多）
CREATE TABLE user_check_groups (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    check_group_id BIGINT UNSIGNED NOT NULL,
    reviewer_id VARCHAR(255) COMMENT 'レビュアーのユーザーID',
    role ENUM('member', 'reviewer', 'admin') NOT NULL DEFAULT 'member' COMMENT 'member: メンバー, reviewer: レビュアー, admin: 管理者',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (check_group_id) REFERENCES check_groups(id),
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id),
    UNIQUE KEY unique_user_group (user_id, check_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェックシートのメインテーブル
CREATE TABLE check_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    description TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    group_id INTEGER REFERENCES check_groups(id),
    status ENUM('open', 'pending', 'rejected', 'closed') NOT NULL DEFAULT 'open' COMMENT 'open: オープン, pending: 承認待ち, rejected: 却下, closed: クローズ',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- インデックスの作成
CREATE INDEX idx_check_items_category_id ON check_items(category_id);
CREATE INDEX idx_check_items_group_id ON check_items(group_id);

-- 質問回答テーブル
CREATE TABLE questions_answers (
    id SERIAL PRIMARY KEY,
    question TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '質問内容',
    answer TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '回答内容',
    questioner_id VARCHAR(255) NOT NULL COMMENT '質問者のユーザーID',
    answerer_id VARCHAR(255) COMMENT '回答者のユーザーID',
    check_group_id BIGINT UNSIGNED NOT NULL COMMENT 'チェックグループID',
    title VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '質問タイトル',
    priority ENUM('low', 'medium', 'high', 'urgent') NOT NULL DEFAULT 'medium' COMMENT '優先度',
    category VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'カテゴリ',
    tags JSON COMMENT 'タグ（JSON配列）',
    is_private BOOLEAN NOT NULL DEFAULT FALSE COMMENT '非公開フラグ',
    is_faq BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'FAQフラグ',
    view_count INTEGER NOT NULL DEFAULT 0 COMMENT '閲覧回数',
    status ENUM('open', 'answered', 'closed') NOT NULL DEFAULT 'open' COMMENT 'open: 未回答, answered: 回答済み, closed: クローズ',
    answered_at TIMESTAMP NULL COMMENT '回答日時',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (questioner_id) REFERENCES users(user_id),
    FOREIGN KEY (answerer_id) REFERENCES users(user_id),
    FOREIGN KEY (check_group_id) REFERENCES check_groups(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 質問回答テーブルのインデックス
CREATE INDEX idx_questions_answers_questioner_id ON questions_answers(questioner_id);
CREATE INDEX idx_questions_answers_answerer_id ON questions_answers(answerer_id);
CREATE INDEX idx_questions_answers_check_group_id ON questions_answers(check_group_id);
CREATE INDEX idx_questions_answers_status ON questions_answers(status);
CREATE INDEX idx_questions_answers_created_at ON questions_answers(created_at);

-- チェック項目の注意事項テーブル
CREATE TABLE check_item_notes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL COMMENT '注意事項を作成したユーザーID',
    check_id BIGINT UNSIGNED NOT NULL COMMENT 'check_itemsテーブルのidを参照',
    note_text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '注意事項の内容',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (check_id) REFERENCES check_items(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- チェック項目注意事項テーブルのインデックス
CREATE INDEX idx_check_item_notes_user_id ON check_item_notes(user_id);
CREATE INDEX idx_check_item_notes_check_id ON check_item_notes(check_id);
CREATE INDEX idx_check_item_notes_created_at ON check_item_notes(created_at);
