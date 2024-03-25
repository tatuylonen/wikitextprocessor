-- https://github.com/wikimedia/mediawiki-extensions-Wikibase/blob/master/client/includes/DataAccess/Scribunto/mw.wikibase.entity.lua

local Entity = {}
local metatable = {}
local methodtable = {}

metatable.__index = methodtable

-- Claim ranks (Claim::RANK_* in PHP)
Entity.claimRanks = {
	RANK_TRUTH = 3,
	RANK_PREFERRED = 2,
	RANK_NORMAL = 1,
	RANK_DEPRECATED = 0
}

-- Is this a valid property id (Pnnn)?
--
-- @param {string} propertyId
local function isValidPropertyId( propertyId )
	return type( propertyId ) == 'string' and propertyId:match( '^P[1-9]%d*$' )
end

-- Create new entity object from given data
--
-- @param {table} data
function Entity.create(data)
    if type(data) ~= 'table' then
        error('Expected a table obtained via mw.wikibase.getEntityObject, got ' .. type(data) .. ' instead')
    end
    if next(data) == nil then
        error('Expected a non-empty table obtained via mw.wikibase.getEntityObject')
    end
    if type(data.schemaVersion) ~= 'number' then
        error('data.schemaVersion must be a number, got ' .. type(data.schemaVersion) .. ' instead')
    end
    if data.schemaVersion < 2 then
        error('mw.wikibase.entity must not be constructed using legacy data')
    end
    if type(data.id) ~= 'string' then
        error('data.id must be a string, got ' .. type(data.id) .. ' instead')
    end

    local entity = data

    setmetatable(entity, metatable)
    return entity
end

-- Get the id serialization from this entity.
function methodtable.getId(entity)
    return entity.id
end

-- Get a term of a given type for a given language code or the content language (on monolingual wikis)
-- or the user's language (on multilingual wikis).
-- Second return parameter is the language the term is in.
--
-- @param {table} entity
-- @param {string} termType A valid key in the entity table (either labels, descriptions or aliases)
-- @param {string|number} langCode
local function getTermAndLang(entity, termType, langCode)
    langCode = langCode or "en"  -- TODO

    if langCode == nil then
        return nil, nil
    end

    if entity[termType] == nil then
        return nil, nil
    end

    local term = entity[termType][langCode]

    if term == nil then
        return nil, nil
    end

    local actualLang = term.language or langCode
    return term.value, actualLang
end

-- Get the label for a given language code or the content language (on monolingual wikis)
-- or the user's language (on multilingual wikis).
--
-- @param {string|number} [langCode]
function methodtable.getLabel( entity, langCode )
	local label = getTermAndLang( entity, 'labels', langCode )
	return label
end

-- Get the description for a given language code or the content language (on monolingual wikis)
-- or the user's language (on multilingual wikis).
--
-- @param {string|number} [langCode]
function methodtable.getDescription(entity, langCode)
    local description = getTermAndLang(entity, 'descriptions', langCode)
    return description
end

-- Get the label for a given language code or the content language (on monolingual wikis)
-- or the user's language (on multilingual wikis).
-- Has the language the returned label is in as an additional second return parameter.
--
-- @param {string|number} [langCode]
function methodtable.getLabelWithLang(entity, langCode)
    return getTermAndLang(entity, 'labels', langCode)
end

-- Get the description for a given language code or the content language (on monolingual wikis)
-- or the user's language (on multilingual wikis).
-- Has the language the returned description is in as an additional second return parameter.
--
-- @param {string|number} [langCode]
function methodtable.getDescriptionWithLang(entity, langCode)
    return getTermAndLang(entity, 'descriptions', langCode)
end

-- Get the sitelink title linking to the given site id
--
-- @param {string|number} [globalSiteId]
function methodtable.getSitelink(entity, globalSiteId)
    if entity.sitelinks == nil then
        return nil
    end

    globalSiteId = globalSiteId or "enwiki"  -- TODO

    if globalSiteId == nil then
        return nil
    end

    local sitelink = entity.sitelinks[globalSiteId]

    if sitelink == nil then
        return nil
    end

    return sitelink.title
end

-- @param {table} entity
-- @param {string} propertyLabelOrId
-- @param {string} funcName for error logging
local function getEntityStatements(entity, propertyLabelOrId, funcName)
    if not entity.claims then
        return {}
    end

    local propertyId = propertyLabelOrId
    if not isValidPropertyId(propertyId) then
        propertyId = mw.wikibase.resolvePropertyId(propertyId)
    end

    if propertyId and entity.claims[propertyId] then
        return entity.claims[propertyId]
    end

    return {}
end

-- Get the best statements with the given property id or label
--
-- @param {string} propertyLabelOrId
function methodtable.getBestStatements(entity, propertyLabelOrId)
    local entityStatements = getEntityStatements(entity, propertyLabelOrId, 'getBestStatements')
    local statements = {}
    local bestRank = 'normal'

    local i = 0
    for _, statement in pairs(entityStatements) do
        if statement.rank == bestRank then
            i = i + 1
            statements[i] = statement
        elseif statement.rank == 'preferred' then
            i = 1
            statements = { statement }
            bestRank = 'preferred'
        end
    end

    return statements
end

-- Get all statements with the given property id or label
--
-- @param {string} propertyLabelOrId
function methodtable.getAllStatements( entity, propertyLabelOrId )
	return getEntityStatements( entity, propertyLabelOrId, 'getAllStatements' )
end

-- Get a table with all property ids attached to the entity.
function methodtable.getProperties(entity)
    if entity.claims == nil then
        return {}
    end

    -- Get the keys (property ids)
    local properties = {}

    local n = 0
    for k, _ in pairs(entity.claims) do
        n = n + 1
        properties[n] = k
    end

    return properties
end

-- Format the main Snaks belonging to a Statement (which is identified by a NumericPropertyId
-- or the label of a Property) as wikitext escaped plain text.
--
-- @param {string} propertyLabelOrId
-- @param {table} [acceptableRanks]
function methodtable.formatPropertyValues(entity, propertyLabelOrId, acceptableRanks)
    return methodtable.getProperties(entity)
end

-- Format the main Snaks belonging to a Statement (which is identified by a NumericPropertyId
-- or the label of a Property) as rich wikitext.
--
-- @param {string} propertyLabelOrId
-- @param {table} [acceptableRanks]
function methodtable.formatStatements(entity, propertyLabelOrId, acceptableRanks)
    return methodtable.getAllStatements(entity)
end

mw.wikibase.entity = Entity
package.loaded['mw.wikibase.entity'] = Entity
return Entity
