DROP TRIGGER IF EXISTS trg_update_fts ON document_chunks;

CREATE TRIGGER trg_update_fts
BEFORE INSERT OR UPDATE OF content ON document_chunks
FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(fts, 'chinese', content);