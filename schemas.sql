CREATE TABLE users (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50),
    user_name VARCHAR(50),
    password VARCHAR(50),
    PRIMARY KEY (id)
);


CREATE TABLE voter_visits (
    id INT NOT NULL AUTO_INCREMENT,
    voter_id VARCHAR(20),
    visited_by INT,
    visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_voter_id (voter_id),
    CONSTRAINT fk_visited_by_user
        FOREIGN KEY (visited_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE TABLE login_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    user_name VARCHAR(100),
    ip_address VARCHAR(45),
    login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status ENUM('success', 'failed') DEFAULT 'success',
    user_agent TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_login_time (login_time),
    INDEX idx_ip_address (ip_address)
);