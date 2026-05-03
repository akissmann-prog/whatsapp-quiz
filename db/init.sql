CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    options JSONB NOT NULL,
    correct_index INTEGER NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS poll_sessions (
    id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(id),
    poll_id VARCHAR(255) UNIQUE NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS responses (
    id SERIAL PRIMARY KEY,
    poll_session_id INTEGER REFERENCES poll_sessions(id),
    participant_phone VARCHAR(50) NOT NULL,
    participant_name VARCHAR(255),
    selected_option INTEGER NOT NULL,
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMP NOT NULL,
    response_time_seconds FLOAT
);

CREATE TABLE IF NOT EXISTS ranking (
    id SERIAL PRIMARY KEY,
    participant_phone VARCHAR(50) UNIQUE NOT NULL,
    participant_name VARCHAR(255),
    total_correct INTEGER DEFAULT 0,
    total_responses INTEGER DEFAULT 0,
    avg_response_time FLOAT DEFAULT 0,
    score FLOAT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO questions (text, options, correct_index, category) VALUES
    ('Qual é a capital do Brasil?', '["São Paulo", "Brasília", "Rio de Janeiro", "Salvador"]', 1, 'geografia'),
    ('Quanto é 15 × 7?', '["95", "100", "105", "110"]', 2, 'matematica'),
    ('Qual linguagem usa indentação obrigatória?', '["Java", "C++", "Python", "JavaScript"]', 2, 'programacao'),
    ('Em que ano o homem pisou na Lua pela primeira vez?', '["1965", "1967", "1969", "1972"]', 2, 'historia'),
    ('Qual é o maior planeta do sistema solar?', '["Saturno", "Urano", "Netuno", "Júpiter"]', 3, 'ciencias')
ON CONFLICT DO NOTHING;
