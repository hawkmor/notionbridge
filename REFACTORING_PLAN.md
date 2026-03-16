# Refactoring Plan

## Current Status

Project has been cleaned up to MVP state:
- ✅ Removed all Docker files
- ✅ Archived frontend code
- ✅ Removed test files
- ✅ Kept only core backend (7 files)

## Current Issues

### 1. Code Organization
- [ ] app/xhs.py is too large (700+ lines)
- [ ] Mixed concerns (scraping, modal extraction, cookie management)
- [ ] Hard-coded selectors scattered throughout

### 2. Configuration
- [ ] Config validation could be improved
- [ ] No clear separation between required/optional configs
- [ ] Cookie file path hard-coded in multiple places

### 3. Error Handling
- [ ] Inconsistent error handling across modules
- [ ] Silent failures in some places
- [ ] No retry logic for network requests

### 4. Logging
- [ ] Logging levels not consistently used
- [ ] Mix of print() and logger calls
- [ ] Verbose output clutters user-level logs

### 5. Testing
- [ ] No unit tests
- [ ] No integration tests
- [ ] Manual testing only

## Proposed Refactoring

### Phase 1: Code Organization

**Split xhs.py into modules:**
- `xhs/scraper.py` - Main scraping logic
- `xhs/selectors.py` - CSS selectors configuration
- `xhs/modal.py` - Modal extraction logic
- `xhs/cookies.py` - Cookie management

**Benefits:**
- Easier to maintain
- Clear separation of concerns
- Easier to test individual components

### Phase 2: Improve Configuration

**Create config schema:**
- Define required vs optional configs
- Add validation with clear error messages
- Centralize all file paths

**Benefits:**
- Better error messages
- Easier to add new configs
- Single source of truth

### Phase 3: Error Handling

**Add retry logic:**
- Network requests with exponential backoff
- Graceful degradation for non-critical failures
- Clear error messages for user

**Benefits:**
- More robust
- Better user experience
- Easier debugging

### Phase 4: Logging

**Standardize logging:**
- Remove all print() calls
- Use logger consistently
- Clear log levels (user/debug/verbose)

**Benefits:**
- Professional logging
- Easier debugging
- Better user experience

### Phase 5: Testing

**Add tests:**
- Unit tests for core functions
- Integration tests for API calls
- Mock data for testing

**Benefits:**
- Catch bugs early
- Easier refactoring
- Better code quality

## Implementation Order

1. **Week 1**: Code organization (split xhs.py)
2. **Week 2**: Configuration improvements
3. **Week 3**: Error handling and retry logic
4. **Week 4**: Logging standardization
5. **Week 5**: Add basic tests

## Success Criteria

- [ ] All modules < 300 lines
- [ ] Clear separation of concerns
- [ ] Comprehensive error handling
- [ ] Consistent logging
- [ ] >80% test coverage

## Notes

- Keep MVP functional during refactoring
- Make incremental changes
- Test after each change
- Document as we go
