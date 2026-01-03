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

