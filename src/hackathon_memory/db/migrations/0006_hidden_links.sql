-- A link of a project can lead to a profile on a social site, such as "t.me/name". The tool
-- cannot tell a bot of the project from a person there, and it keeps no handle of a person
-- (design 5.4, design rule 11). So such a link is kept without its address: the row says that
-- the link is there and on which site. A card sends the reader to the page of the project.
ALTER TABLE links ALTER COLUMN url DROP NOT NULL;
ALTER TABLE links ADD COLUMN hidden_on text CHECK (hidden_on <> '');
-- A link has its address, or the site of its hidden address. Never both, and never neither.
ALTER TABLE links ADD CONSTRAINT links_address_or_hidden_site
    CHECK ((url IS NULL) <> (hidden_on IS NULL));
