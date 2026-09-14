# Banco de dados

`schema.sql` documenta a estrutura principal do PostgreSQL.

O runtime do backend também registra os modelos SQLAlchemy em `backend/app/models.py`. Em produção, não use `schema.sql` como substituto de migrations incrementais sem revisar o estado real do banco.
